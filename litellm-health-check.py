#!/usr/bin/env python3
import os
import sys
import yaml
import time
import json
import argparse
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed

# ANSI Terminal Colors
COLOR_GREEN = "\033[92m"
COLOR_RED = "\033[91m"
COLOR_YELLOW = "\033[93m"
COLOR_MAGENTA = "\033[95m"
COLOR_BLUE = "\033[94m"
COLOR_CYAN = "\033[96m"
COLOR_RESET = "\033[0m"
COLOR_BOLD = "\033[1m"

def log_info(msg):
    print(f"{COLOR_BLUE}[INFO]{COLOR_RESET} {msg}")

def log_success(msg):
    print(f"{COLOR_GREEN}[SUCCESS]{COLOR_RESET} {msg}")

def log_warning(msg):
    print(f"{COLOR_YELLOW}[WARNING]{COLOR_RESET} {msg}")

def log_error(msg):
    print(f"{COLOR_RED}[ERROR]{COLOR_RESET} {msg}")

def get_provider(model_name, underlying_model):
    """Detect provider based on model name and underlying model path."""
    model_name_lower = model_name.lower()
    underlying_lower = underlying_model.lower()

    if "gemini" in model_name_lower or "gemini" in underlying_lower:
        return "Google Gemini"
    elif "cerebras" in model_name_lower or "cerebras" in underlying_lower:
        return "Cerebras"
    elif "nvidia_nim" in underlying_lower or "nvidia/" in model_name_lower or "nvidia/" in underlying_lower or "nim" in underlying_lower:
        return "Nvidia NIM"
    elif "mistral" in model_name_lower or "mistral" in underlying_lower:
        return "Mistral"
    elif "opencode" in underlying_lower or "nemotron" in model_name_lower or "big-pickle" in model_name_lower or "deepseek-v4-flash-free" in model_name_lower:
        return "OpenCode Zen"
    elif "lite-llm" in model_name_lower or "auto_router" in underlying_lower or "complexity" in model_name_lower:
        return "LiteLLM Routing"
    else:
        return "Other"

def is_embedding_model(model_name, underlying_model):
    """Determine if a model is an embedding model."""
    model_name_lower = model_name.lower()
    underlying_lower = underlying_model.lower()
    return "embed" in model_name_lower or "embed" in underlying_lower or "embedding" in model_name_lower or "embedding" in underlying_lower

def load_models_from_config(config_path):
    """Load and parse the list of models from the YAML configuration."""
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found at: {config_path}")

    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    model_list = config.get("model_list", [])
    models = []
    for item in model_list:
        name = item.get("model_name")
        if not name:
            continue
        params = item.get("litellm_params", {})
        underlying = params.get("model", "N/A")

        models.append({
            "model_name": name,
            "underlying_model": underlying,
            "provider": get_provider(name, underlying),
            "is_embedding": is_embedding_model(name, underlying)
        })
    return models

def check_single_model(model_info, base_url, api_key, prompt, embedding_input, timeout):
    """Perform health check on a single model (chat or embedding)."""
    import openai

    model_name = model_info["model_name"]
    is_embed = model_info["is_embedding"]
    provider = model_info["provider"]
    underlying = model_info["underlying_model"]

    # Initialize OpenAI client pointed to LiteLLM endpoint
    client = openai.OpenAI(base_url=base_url, api_key=api_key)

    start_time = time.time()
    ttft = None
    response_content = ""
    status_code = None
    error_type = None
    error_message = None

    try:
        if is_embed:
            # Embedding check
            resp = client.embeddings.create(
                model=model_name,
                input=embedding_input,
                timeout=timeout
            )
            total_time = time.time() - start_time
            # Get dimension
            vector_dim = len(resp.data[0].embedding) if (resp.data and len(resp.data) > 0) else 0
            response_content = f"Success! Returned embedding vector with dimension {vector_dim}."
            status = "HEALTHY"
            status_code = 200
        else:
            # Chat completion check with streaming
            stream = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                stream=True,
                timeout=timeout
            )

            for chunk in stream:
                if chunk.choices and len(chunk.choices) > 0:
                    delta = chunk.choices[0].delta
                    content = getattr(delta, "content", None)
                    if content:
                        if ttft is None:
                            ttft = time.time() - start_time
                        response_content += content

            total_time = time.time() - start_time
            status = "HEALTHY"
            status_code = 200

    except Exception as e:
        total_time = time.time() - start_time
        error_type = type(e).__name__
        error_message = str(e)

        # Extract HTTP status code from OpenAI errors if possible
        if hasattr(e, "status_code"):
            status_code = e.status_code
        elif hasattr(e, "response") and hasattr(e.response, "status_code"):
            status_code = e.response.status_code

        # Determine status classification
        if "timeout" in error_message.lower() or "timed out" in error_message.lower() or isinstance(e, openai.APITimeoutError):
            status = "TIMEOUT"
        elif "connection" in error_message.lower() or isinstance(e, openai.APIConnectionError):
            status = "CONNECTION_ERROR"
        else:
            status = "UNHEALTHY"

    # Calculate word/character counts for chat models
    word_count = len(response_content.split()) if response_content else 0
    char_count = len(response_content) if response_content else 0
    estimated_tokens = int(char_count / 4) # Standard heuristic

    # Calculate throughput
    throughput_wps = 0.0
    throughput_tps = 0.0
    if not is_embed and status == "HEALTHY" and total_time > 0:
        generation_time = total_time - (ttft or 0)
        if generation_time > 0:
            throughput_wps = word_count / generation_time
            throughput_tps = estimated_tokens / generation_time

    return {
        "model_name": model_name,
        "underlying_model": underlying,
        "provider": provider,
        "is_embedding": is_embed,
        "status": status,
        "total_latency": total_time,
        "ttft": ttft,
        "response_preview": (response_content[:80] + "...") if response_content and len(response_content) > 80 else response_content,
        "word_count": word_count,
        "char_count": char_count,
        "estimated_tokens": estimated_tokens,
        "throughput_wps": throughput_wps,
        "throughput_tps": throughput_tps,
        "status_code": status_code,
        "error_type": error_type,
        "error_message": error_message
    }

def print_console_table(results):
    """Print results as a beautifully formatted console table."""
    print("\n" + "=" * 120)
    print(f" {COLOR_BOLD}LITE-LLM MODEL HEALTH CHECK RESULTS{COLOR_RESET}")
    print("=" * 120)

    header_fmt = "  {:<30} {:<15} {:<15} {:<10} {:<10} {:<10} {:<15}"
    print(header_fmt.format("Model Name", "Provider", "Type", "Status", "TTFT", "Latency", "Error/Details"))
    print("-" * 120)

    row_fmt = "  {:<30} {:<15} {:<15} {:<10} {:<10} {:<10} {:<15}"

    for r in results:
        # Determine status color
        status = r["status"]
        if status == "HEALTHY":
            status_colored = f"{COLOR_GREEN}{status:<10}{COLOR_RESET}"
        elif status == "TIMEOUT":
            status_colored = f"{COLOR_MAGENTA}{status:<10}{COLOR_RESET}"
        elif status == "CONNECTION_ERROR":
            status_colored = f"{COLOR_YELLOW}{status:<10}{COLOR_RESET}"
        else:
            status_colored = f"{COLOR_RED}{status:<10}{COLOR_RESET}"

        mtype = "Embedding" if r["is_embedding"] else "Chat"
        ttft_str = f"{r['ttft']:.2f}s" if r["ttft"] is not None else ("N/A" if r["is_embedding"] else "-")
        latency_str = f"{r['total_latency']:.2f}s"

        # Details or error code
        if r["status"] == "HEALTHY":
            if r["is_embedding"]:
                details_str = f"{COLOR_GREEN}Success{COLOR_RESET}"
            else:
                details_str = f"{COLOR_GREEN}{r['estimated_tokens']} tok / {r['throughput_tps']:.1f} tps{COLOR_RESET}"
        else:
            code_str = f" [HTTP {r['status_code']}]" if r["status_code"] else ""
            details_str = f"{COLOR_RED}{r['error_type'] or 'Error'}{code_str}{COLOR_RESET}"

        print(row_fmt.format(
            r["model_name"][:30],
            r["provider"][:15],
            mtype,
            status_colored,
            ttft_str,
            latency_str,
            details_str
        ))

    print("=" * 120 + "\n")

def generate_markdown_report(results, summary, output_path):
    """Generate a rich and professional Markdown health report."""
    md_content = []

    md_content.append("# LiteLLM Model Health Check Report")
    md_content.append(f"**Report Generated:** {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}  ")
    md_content.append(f"**Configuration Source:** `{summary['config_path']}`  ")
    md_content.append(f"**LiteLLM Base URL:** `{summary['base_url']}`\n")

    md_content.append("## 📊 Summary Dashboard\n")

    # 2x2 table for dashboard
    md_content.append("| Metric | Value | Breakdown / Notes |")
    md_content.append("| :--- | :--- | :--- |")
    md_content.append(f"| **Overall Health Score** | **{summary['health_percentage']:.1f}%** | {summary['healthy_count']} / {summary['total_count']} Models Healthy |")
    md_content.append(f"| **Total Checked** | {summary['total_count']} | {summary['chat_count']} Chat Models, {summary['embed_count']} Embedding Models |")
    md_content.append(f"| **Healthy Models** | {summary['healthy_count']} | Status OK |")
    md_content.append(f"| **Failed/Degraded Models** | {summary['failed_count']} | {summary['unhealthy_count']} Unhealthy, {summary['timeout_count']} Timed Out, {summary['conn_err_count']} Conn Errors |")
    md_content.append(f"| **Average TTFT (Chat)** | {f'{summary['avg_ttft']:.3f}s' if summary['avg_ttft'] is not None else 'N/A'} | Time to first token (healthy chat models only) |")
    md_content.append(f"| **Average Latency (Chat)** | {f'{summary['avg_latency_chat']:.3f}s' if summary['avg_latency_chat'] is not None else 'N/A'} | Total roundtrip latency for healthy chat models |")
    md_content.append(f"| **Average Latency (Embed)** | {f'{summary['avg_latency_embed']:.3f}s' if summary['avg_latency_embed'] is not None else 'N/A'} | Total latency for healthy embedding models |")
    md_content.append("\n")

    md_content.append("## 🏢 Provider-Level Performance Breakdown\n")
    md_content.append("| Provider | Models Checked | Healthy | Unhealthy | Avg Latency | Avg TTFT (Chat) |")
    md_content.append("| :--- | :---: | :---: | :---: | :---: | :---: |")

    for provider, p_stats in summary["providers"].items():
        avg_lat = f"{p_stats['avg_latency']:.2f}s" if p_stats["avg_latency"] is not None else "N/A"
        avg_ttft = f"{p_stats['avg_ttft']:.2f}s" if p_stats["avg_ttft"] is not None else "N/A"
        md_content.append(f"| **{provider}** | {p_stats['total']} | {p_stats['healthy']} | {p_stats['failed']} | {avg_lat} | {avg_ttft} |")
    md_content.append("\n")

    md_content.append("## 🔍 Detailed Model Diagnostics\n")
    md_content.append("| Model Name | Provider | Type | Status | TTFT | Total Latency | Tokens / Vector | Throughput |")
    md_content.append("| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: |")

    for r in results:
        mtype = "Embedding" if r["is_embedding"] else "Chat"

        # Color markdown status using badges or emojis
        status = r["status"]
        if status == "HEALTHY":
            status_badge = "🟢 HEALTHY"
        elif status == "TIMEOUT":
            status_badge = "⏳ TIMEOUT"
        elif status == "CONNECTION_ERROR":
            status_badge = "⚠️ CONN_ERR"
        else:
            status_badge = "🔴 UNHEALTHY"

        ttft_str = f"{r['ttft']:.3f}s" if r["ttft"] is not None else ("N/A" if r["is_embedding"] else "-")
        latency_str = f"{r['total_latency']:.3f}s"

        if r["status"] == "HEALTHY":
            if r["is_embedding"]:
                tok_str = "Vector"
                throughput_str = "N/A"
            else:
                tok_str = f"{r['estimated_tokens']} est."
                throughput_str = f"{r['throughput_tps']:.1f} t/s"
        else:
            tok_str = "-"
            throughput_str = "-"

        md_content.append(f"| `{r['model_name']}` | {r['provider']} | {mtype} | **{status_badge}** | {ttft_str} | {latency_str} | {tok_str} | {throughput_str} |")
    md_content.append("\n")

    # Failed Models Details Section
    failed_models = [r for r in results if r["status"] != "HEALTHY"]
    if failed_models:
        md_content.append("## ❌ Unhealthy / Failed Models Logs\n")
        for r in failed_models:
            md_content.append(f"### 🛑 `{r['model_name']}` ({r['provider']})\n")
            md_content.append(f"- **Underlying Model:** `{r['underlying_model']}`")
            md_content.append(f"- **Status:** `{r['status']}`")
            md_content.append(f"- **HTTP Status Code:** `{r['status_code'] or 'Unknown'}`")
            md_content.append(f"- **Error Class:** `{r['error_type'] or 'N/A'}`")
            md_content.append("- **Error Message:**")
            md_content.append("```text")
            md_content.append(r["error_message"] or "No error message captured.")
            md_content.append("```\n")
            md_content.append("---")

    # Healthy Chat Response Previews Section
    healthy_chats = [r for r in results if r["status"] == "HEALTHY" and not r["is_embedding"]]
    if healthy_chats:
        md_content.append("## 💬 Healthy Model Response Previews\n")
        md_content.append("| Model Name | Response Preview |")
        md_content.append("| :--- | :--- |")
        for r in healthy_chats:
            preview = r["response_preview"].replace("\n", " ").replace("|", "\\|")
            md_content.append(f"| `{r['model_name']}` | {preview} |")
        md_content.append("\n")

    with open(output_path, "w") as f:
        f.write("\n".join(md_content))

    log_success(f"Markdown report written to: {output_path}")

def generate_json_report(results, summary, output_path):
    """Generate a structured JSON health report."""
    report_data = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "summary": summary,
        "results": results
    }
    with open(output_path, "w") as f:
        json.dump(report_data, f, indent=2)

    log_success(f"JSON report written to: {output_path}")

def compute_summary_stats(results, config_path, base_url):
    """Aggregate statistics from the health check results."""
    total_count = len(results)
    healthy_count = sum(1 for r in results if r["status"] == "HEALTHY")
    failed_count = total_count - healthy_count

    unhealthy_count = sum(1 for r in results if r["status"] == "UNHEALTHY")
    timeout_count = sum(1 for r in results if r["status"] == "TIMEOUT")
    conn_err_count = sum(1 for r in results if r["status"] == "CONNECTION_ERROR")

    chat_count = sum(1 for r in results if not r["is_embedding"])
    embed_count = sum(1 for r in results if r["is_embedding"])

    health_percentage = (healthy_count / total_count * 100) if total_count > 0 else 0.0

    # Averages for chat models
    healthy_chats = [r for r in results if r["status"] == "HEALTHY" and not r["is_embedding"]]
    avg_ttft = sum(r["ttft"] for r in healthy_chats) / len(healthy_chats) if healthy_chats else None
    avg_latency_chat = sum(r["total_latency"] for r in healthy_chats) / len(healthy_chats) if healthy_chats else None

    # Averages for embedding models
    healthy_embeds = [r for r in results if r["status"] == "HEALTHY" and r["is_embedding"]]
    avg_latency_embed = sum(r["total_latency"] for r in healthy_embeds) / len(healthy_embeds) if healthy_embeds else None

    # Aggregate by provider
    providers_data = {}
    for r in results:
        prov = r["provider"]
        if prov not in providers_data:
            providers_data[prov] = []
        providers_data[prov].append(r)

    providers_summary = {}
    for prov, p_results in providers_data.items():
        p_total = len(p_results)
        p_healthy = sum(1 for r in p_results if r["status"] == "HEALTHY")
        p_failed = p_total - p_healthy

        # Calculate healthy model latency averages within provider
        p_healthy_models = [r for r in p_results if r["status"] == "HEALTHY"]
        p_avg_lat = sum(r["total_latency"] for r in p_healthy_models) / len(p_healthy_models) if p_healthy_models else None

        # TTFT average for chat models within provider
        p_healthy_chats = [r for r in p_healthy_models if not r["is_embedding"]]
        p_avg_ttft = sum(r["ttft"] for r in p_healthy_chats) / len(p_healthy_chats) if p_healthy_chats else None

        providers_summary[prov] = {
            "total": p_total,
            "healthy": p_healthy,
            "failed": p_failed,
            "avg_latency": p_avg_lat,
            "avg_ttft": p_avg_ttft
        }

    return {
        "config_path": config_path,
        "base_url": base_url,
        "total_count": total_count,
        "healthy_count": healthy_count,
        "failed_count": failed_count,
        "unhealthy_count": unhealthy_count,
        "timeout_count": timeout_count,
        "conn_err_count": conn_err_count,
        "chat_count": chat_count,
        "embed_count": embed_count,
        "health_percentage": health_percentage,
        "avg_ttft": avg_ttft,
        "avg_latency_chat": avg_latency_chat,
        "avg_latency_embed": avg_latency_embed,
        "providers": providers_summary
    }

def main():
    parser = argparse.ArgumentParser(description="LiteLLM Model Health Check Script")
    parser.add_argument("--config", default="/workspace/lite-llm/lite-llm-default.yaml", help="Path to LiteLLM default YAML configuration")
    parser.add_argument("--endpoint", default="http://127.0.0.1:5090/v1", help="Base URL of LiteLLM API")
    parser.add_argument("--api-key", default="dummy", help="API key for LiteLLM")
    parser.add_argument("--timeout", type=float, default=300.0, help="Request timeout per model in seconds")
    parser.add_argument("--prompt", default="tell me about yourself", help="Test prompt for chat completion models")
    parser.add_argument("--embedding-input", default="tell me about yourself", help="Test input for embedding models")
    parser.add_argument("--concurrency", type=int, default=1, help="Max parallel model health checks (default 1 for sequential)")
    parser.add_argument("--output-markdown", default="health_report.md", help="Output path for the Markdown report")
    parser.add_argument("--output-json", default="health_report.json", help="Output path for the JSON report")

    args = parser.parse_args()

    log_info("Starting LiteLLM Health Check Process...")
    log_info(f"Loading configuration from: {args.config}")

    try:
        models = load_models_from_config(args.config)
        log_success(f"Successfully loaded {len(models)} models from config.")
    except Exception as e:
        log_error(f"Failed to load models: {e}")
        sys.exit(1)

    results = []

    if args.concurrency > 1:
        log_info(f"Running health checks with concurrency level: {args.concurrency}")
        with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
            future_to_model = {
                executor.submit(
                    check_single_model,
                    m,
                    args.endpoint,
                    args.api_key,
                    args.prompt,
                    args.embedding_input,
                    args.timeout
                ): m for m in models
            }

            for future in as_completed(future_to_model):
                m = future_to_model[future]
                try:
                    res = future.result()
                    results.append(res)
                    status_color = COLOR_GREEN if res["status"] == "HEALTHY" else (COLOR_MAGENTA if res["status"] == "TIMEOUT" else COLOR_RED)
                    print(f"  Checked: {res['model_name']:<30} -> {status_color}{res['status']}{COLOR_RESET} ({res['total_latency']:.2f}s)")
                except Exception as exc:
                    log_error(f"Model {m['model_name']} generated an unhandled exception: {exc}")
                    traceback.print_exc()
    else:
        log_info("Running health checks sequentially...")
        for idx, m in enumerate(models, 1):
            print(f"  [{idx}/{len(models)}] Checking {m['model_name']} ... ", end="", flush=True)
            res = check_single_model(
                m,
                args.endpoint,
                args.api_key,
                args.prompt,
                args.embedding_input,
                args.timeout
            )
            results.append(res)
            status_color = COLOR_GREEN if res["status"] == "HEALTHY" else (COLOR_MAGENTA if res["status"] == "TIMEOUT" else COLOR_RED)
            print(f"{status_color}{res['status']}{COLOR_RESET} ({res['total_latency']:.2f}s)")

    # Re-order results to match original config ordering
    results_map = {r["model_name"]: r for r in results}
    ordered_results = [results_map[m["model_name"]] for m in models if m["model_name"] in results_map]

    # Compute aggregates
    summary = compute_summary_stats(ordered_results, args.config, args.endpoint)

    # Output Table to Console
    print_console_table(ordered_results)

    # Generate Files
    generate_markdown_report(ordered_results, summary, args.output_markdown)
    generate_json_report(ordered_results, summary, args.output_json)

    # Summary Line
    print(f"{COLOR_BOLD}SUMMARY:{COLOR_RESET}")
    print(f"  Total Checked: {summary['total_count']}")
    print(f"  Healthy:       {COLOR_GREEN}{summary['healthy_count']}{COLOR_RESET}")
    print(f"  Failed:        {COLOR_RED}{summary['failed_count']}{COLOR_RESET}")
    print(f"  Health Score:  {COLOR_BOLD}{summary['health_percentage']:.1f}%{COLOR_RESET}")

    # Check if the overall health check should exit with 0 or non-zero code.
    # Usually we exit with 0 to complete successfully unless litellm itself was completely down.
    if summary["conn_err_count"] == len(models):
        log_error("All models failed with connection errors. LiteLLM is likely offline!")
        sys.exit(2)

    log_success("All checks completed successfully!")

if __name__ == "__main__":
    main()
