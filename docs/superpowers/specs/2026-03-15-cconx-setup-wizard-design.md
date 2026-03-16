# cconx Setup Wizard Design Specification

## Overview

This document specifies the design for adding a setup wizard to the cconx tool that allows users to configure the global configuration file through an interactive command-line interface.

## Purpose

The setup wizard (`cconx setup`) will provide an intuitive way for users to configure all aspects of the ClaudeConX Docker management tool without manually editing JSON configuration files. The wizard will walk users through each configuration field, explain its purpose, provide sensible defaults, and validate user inputs.

## Requirements

### Core Requirements
- Invoked via `cconx setup` command
- Walk through each field of the global config file
- Explain each field's purpose and usage
- Show current value if exists, otherwise show default
- Provide sensible default values
- Perform basic format validation
- Preserve existing values when config file already exists
- Allow user to exit midway with save/discard option

### Environment Variables Handling
- Explicitly configure special ClaudeConX container environment variables
- Allow arbitrary additional environment variables
- Avoid configuring internal cconx-managed variables
- Organize environment variables by functional groups

## Architecture

### Command Integration
- Add `setup` command to `cconx/cli.py` argument parser
- Create `setup_command` function that orchestrates the wizard
- Integrate with existing `ConfigManager` class

### Modular Field Handler Design
```python
class FieldHandler:
    def prompt(self, current_value): ...
    def validate(self, input_value): ...
    def format(self, input_value): ...
    def get_default(self): ...
    def get_explanation(self): ...

class SetupWizard:
    def __init__(self, config_manager): ...
    def run(self): ...
    def _process_field_group(self, group_name, field_handlers): ...
```

## Field Organization

### Group 1: Instance Management
- `port_range`: Min/max ports for instance allocation (currently: min=8000, max=9000)
- `ide_address_template`: URL template for IDE access (currently: "http://localhost:{port}")

### Group 2: Docker Configuration
- `default_image`: Default Docker image (currently: "tylercollison2089/vscode-claude:latest")
- `docker_network`: Docker network name (currently: None)
- `dns_servers`: List of DNS server IPs (currently: None)

### Group 3: Volumes & Environment
- `enabled_volumes`: List of volume paths to mount (currently: [])
- `include_docker_sock`: Boolean for Docker socket mounting (currently: True)
- `environment`: Global environment variables dict (currently: {})

### Environment Variables Handling

#### Phase 1 Approach: Explicit Special Variable Prompts

**API Keys & Authentication** (explicitly prompted):
- `NIM_API_KEY`: NVIDIA NIM API key
- `GOOGLE_API_KEY`: Google AI Studio API key
- `MISTRAL_API_KEY`: Mistral AI API key
- `OPENROUTER_API_KEY`: OpenRouter API key

**Container Configuration** (explicitly prompted):
- `PUID`: User ID for container processes
- `PGID`: Group ID for container processes
- `TZ`: Timezone configuration
- `PROXY_DOMAIN`: Reverse proxy domain for external access
- `DEFAULT_WORKSPACE`: Default workspace directory
- `PWA_APPNAME`: Progressive Web App name

**Authentication & Access Control** (explicitly prompted):
- `PASSWORD`: Plaintext password for VS Code web interface
- `HASHED_PASSWORD`: Argon2id-hashed password
- `SUDO_PASSWORD`: Plaintext sudo password
- `SUDO_PASSWORD_HASH`: Hashed sudo password

**Claude Code Configuration** (explicitly prompted):
- `CLAUDE_CODE_PERMISSION_MODE`: Permission mode (`acceptEdits`, `bypassPermissions`, `default`, `plan`, `dontAsk`)
- `CLAUDE_MARKETPLACES`: Comma-separated list of plugin marketplaces
- `CLAUDE_PLUGINS`: Comma-separated list of plugins to install

**Claude Code Router Configuration** (explicitly prompted):
- `CCR_PROFILE`: Claude Code Router profile to activate automatically

**Claude Threads Configuration** (explicitly prompted if ENABLE_THREADS=true):
- `ENABLE_THREADS`: Enable Claude Threads server
- `MM_ADDRESS`: Mattermost server URL
- `MM_TOKEN`: Mattermost bot authentication token
- `MM_TEAM`: Mattermost team name
- `MM_BOT_NAME`: Bot display name
- `THREADS_CHROME`: Chrome executable path
- `THREADS_WORKTREE_MODE`: Git worktree mode
- `THREADS_SKIP_PERMISSIONS`: Skip permission prompts

**Git Repository Setup** (explicitly prompted):
- `GIT_REPO_URL`: Repository URL to clone on startup
- `GIT_BRANCH_NAME`: Branch name

**Knowledge Repository Integration** (explicitly prompted):
- `KNOWLEDGE_REPOS`: Git repos with markdown files to load into CLAUDE.md

**Strategy**:
- **Explicit Prompts**: Walk user through each special variable with explanation
- **Context-Sensitive Help**: Provide usage examples and implications
- **Conditional Prompts**: Only show Claude Threads prompts if `ENABLE_THREADS=true`
- **Validation**: Basic format validation for API keys, URLs, and values
- **Arbitrary Variables**: Allow adding additional variables after special ones
- **Internal Variables Notice**: Warn about cconx-managed variables (`MM_CHANNEL`, etc.)

## User Interaction Flow

1. **Welcome Message**
   - Explain wizard purpose
   - Show current config file location
   - Explain save/discard options

2. **Group-by-Group Progression**
   - Clear section headers for each group
   - Show group purpose and relevance

3. **Field-by-Field Configuration**
   - Display field explanation with context-sensitive detail
   - Show current value (if exists) or default value
   - Accept user input with validation
   - Allow skipping fields (keep current/default)

4. **Environment Variables Special Handling**
   - **Explicit Prompts**: Walk through each special ClaudeConX variable
   - **Group Organization**: Present variables by functional groups (Container, API Keys, Claude Code)
   - **Required/Optional Indicators**: Clearly mark which variables are essential
   - **Examples & Context**: Provide usage examples and implications
   - **Arbitrary Variables**: Allow adding additional variables after special ones
   - **Internal Variables Notice**: Warn about cconx-managed variables (`MM_CHANNEL`, etc.)

5. **Confirmation Step**
   - Show summary of changes
   - Ask for final confirmation
   - Provide save/discard option

6. **Save Configuration**
   - Write validated configuration to file
   - Show success message
   - Provide next steps guidance

## Validation Rules

### Port Range
- Both values must be integers
- Min port < max port
- Ports must be in valid range (1-65535)

### Docker Network
- Must be valid Docker network name
- Optional network existence checking (defer to Phase 2 to avoid external API calls)

### DNS Servers
- Must be valid IP addresses (IPv4 or IPv6)
- Filter invalid addresses with warnings

### Volume Paths
- Must start with `/`
- Must be valid paths

### Environment Variables
- Key=value format validation
- Special validation for API keys (format checking)
- Complex formats (comma-separated lists) validation

## Implementation Details

### File Structure
```
cconx/
├── cli.py              # Add setup_command function
├── config.py           # Add SetupWizard and FieldHandler classes
├── wizard/             # Optional: dedicated wizard module
│   ├── __init__.py
│   ├── setup_wizard.py
│   └── field_handlers/
└── tests/
    └── test_setup_wizard.py
```

### CLI Integration
Add to `cconx/cli.py` argument parser:
```python
# Setup command
setup_parser = subparsers.add_parser("setup", help="Interactive configuration wizard")
```

Integration with existing `ConfigManager._save_config()` method.

### Field Handler Examples

#### PortRangeFieldHandler
```python
class PortRangeFieldHandler(FieldHandler):
    def get_explanation(self):
        return "Defines the port range for automatically assigning ports to new instances"

    def prompt(self, current_value):
        # Show current min/max, get new values
        # Handle dict input/output
        pass

    def validate(self, min_port, max_port):
        # Check integer types, valid range, min < max
        pass
```

#### EnvironmentFieldHandler
```python
class EnvironmentFieldHandler(FieldHandler):
    def prompt(self, current_value):
        # Present subgroups sequentially
        # Handle complex dict structure
        pass

    def validate(self, env_dict):
        # Validate each subgroup's requirements
        pass
```

## Testing Strategy

### Unit Tests
- Test each FieldHandler class individually
- Test validation logic for all field types
- Test default value generation

### Integration Tests
- Test full wizard flow
- Test config file reading/writing
- Test backward compatibility

### CLI Tests
- Test `cconx setup` command integration
- Test error handling and edge cases

## Error Handling

### User Input Errors
- Clear error messages with examples
- Retry prompts for invalid inputs
- Option to skip problematic fields

### System Errors
- Graceful handling of file I/O errors
- Clear error messages for Docker network issues
- Fallback to default values when appropriate

### Keyboard Interrupt
- Handle Ctrl+C gracefully
- Ask user whether to save/discard progress
- Preserve partial configuration if requested

## Implementation Phases

### Phase 1: MVP Implementation
- Core wizard framework with FieldHandler classes
- Basic field handlers for essential fields: `port_range`, `default_image`, `enabled_volumes`, `include_docker_sock`
- **Comprehensive environment variable handling with explicit prompts for ALL special ClaudeConX variables**
  - API Keys & Authentication
  - Container Configuration
  - Claude Code Settings
  - Claude Code Router
  - Claude Threads (conditional)
  - Git Integration
  - Knowledge Repositories
- Basic validation without external API calls
- CLI integration with `cconx setup` command

### Phase 2: Advanced Features
- Complex field handlers: `docker_network`, `dns_servers`
- Enhanced environment variable validation (URL checking, format validation)
- External validation (Docker network existence checking)
- Enhanced error handling and user experience

### Phase 3: Polish & Testing
- Comprehensive testing suite
- Performance optimization
- User documentation updates
- Bug fixes and refinement

## Backward Compatibility

### Existing Config Files
- Preserve all existing values
- Add new fields with sensible defaults
- Maintain existing file format and structure

### Field Changes
- Handle missing fields in old configs
- Provide migration path for deprecated fields
- Maintain compatibility with existing instances

## Security Considerations

### Sensitive Data
- API keys and tokens handled securely
- No logging of sensitive information
- Clear warnings about security implications

### File Permissions
- Ensure config file has appropriate permissions
- Warn about world-readable config files with sensitive data

## Performance Considerations

### Wizard Responsiveness
- Minimal delay between prompts
- Fast validation without external calls (where possible)
- Efficient config file reading/writing

### Docker Network Validation
- Optional network existence checking
- Fast failure if network doesn't exist
- Clear instructions for network creation

## Success Criteria

### Functional
- Users can fully configure cconx through the wizard
- All configuration fields are properly handled
- Validation prevents invalid configurations
- Backward compatibility maintained

### User Experience
- Wizard is intuitive and easy to use
- Clear explanations and helpful defaults
- Graceful error handling and recovery
- Fast and responsive interaction

### Technical
- Code is maintainable and testable
- Integration with existing codebase is clean
- Performance meets user expectations
- Security considerations addressed

## Next Steps

1. **Implementation Planning** - Create detailed implementation plan
2. **Development** - Implement wizard functionality
3. **Testing** - Comprehensive testing of all features
4. **Documentation** - Update user documentation
5. **Release** - Deploy and gather user feedback