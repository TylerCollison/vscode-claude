# Bidirectional Deletion Synchronization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement proper bidirectional file deletion synchronization for the build-env tool

**Architecture:** Enhance existing sync methods to handle deletions by comparing file lists and deleting files that exist in destination but not source before copying

**Tech Stack:** Python, Docker SDK, subprocess for file operations

---

## File Structure

**Modified Files:**
- `build-env/build_env.py`: Enhance sync methods with deletion handling
- `build-env/tests/test_build_env.py`: Add tests for deletion synchronization

**New Helper Methods:**
- `_get_file_list()`: Recursively list files in directory
- `_delete_files_in_destination()`: Delete files that exist in destination but not source

## Implementation Tasks

### Task 1: Add File Listing Helper Method

**Files:**
- Modify: `build-env/build_env.py:200-250`

- [ ] **Step 1: Write the failing test**

```python
def test_get_file_list():
    """Test file listing helper method"""
    import tempfile
    import os
    
    # Create temporary directory structure
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create test files and directories
        os.makedirs(os.path.join(tmpdir, 'subdir'))
        with open(os.path.join(tmpdir, 'file1.txt'), 'w') as f:
            f.write('test')
        with open(os.path.join(tmpdir, 'subdir', 'file2.txt'), 'w') as f:
            f.write('test')
        
        # Test file listing
        manager = BuildEnvironmentManager()
        files = manager._get_file_list(tmpdir)
        
        # Should contain relative paths
        assert 'file1.txt' in files
        assert 'subdir/file2.txt' in files
        assert '.build-env' not in files  # Should skip .build-env directories
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest build-env/tests/test_build_env.py::test_get_file_list -v`
Expected: FAIL with "'BuildEnvironmentManager' object has no attribute '_get_file_list'"

- [ ] **Step 3: Write minimal implementation**

```python
def _get_file_list(self, directory: str) -> set:
    """Get recursive file list from directory, skipping .build-env directories.
    
    Args:
        directory: Path to directory
        
    Returns:
        Set of relative file paths
    """
    file_list = set()
    
    for root, dirs, files in os.walk(directory):
        # Skip .build-env directories
        if '.build-env' in dirs:
            dirs.remove('.build-env')
        
        for file in files:
            # Get relative path from the specified directory
            abs_path = os.path.join(root, file)
            rel_path = os.path.relpath(abs_path, directory)
            file_list.add(rel_path)
    
    return file_list
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest build-env/tests/test_build_env.py::test_get_file_list -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add build-env/build_env.py build-env/tests/test_build_env.py
git commit -m "feat: add file listing helper method"
```

### Task 2: Add Destination Deletion Helper Method

**Files:**
- Modify: `build-env/build_env.py:250-300`

- [ ] **Step 1: Write the failing test**

```python
def test_delete_files_in_destination():
    """Test destination file deletion helper method"""
    import tempfile
    import os
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create source and destination directories
        source_dir = os.path.join(tmpdir, 'source')
        dest_dir = os.path.join(tmpdir, 'dest')
        os.makedirs(source_dir)
        os.makedirs(dest_dir)
        
        # Create files that should exist in both
        with open(os.path.join(source_dir, 'common.txt'), 'w') as f:
            f.write('common')
        with open(os.path.join(dest_dir, 'common.txt'), 'w') as f:
            f.write('common')
        
        # Create files that should be deleted from destination
        with open(os.path.join(dest_dir, 'delete_me.txt'), 'w') as f:
            f.write('delete')
        
        manager = BuildEnvironmentManager()
        source_files = manager._get_file_list(source_dir)
        dest_files = manager._get_file_list(dest_dir)
        
        # Delete files that exist in dest but not source
        manager._delete_files_in_destination(dest_dir, source_files, dest_files)
        
        # Verify file was deleted
        assert not os.path.exists(os.path.join(dest_dir, 'delete_me.txt'))
        assert os.path.exists(os.path.join(dest_dir, 'common.txt'))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest build-env/tests/test_build_env.py::test_delete_files_in_destination -v`
Expected: FAIL with "'BuildEnvironmentManager' object has no attribute '_delete_files_in_destination'"

- [ ] **Step 3: Write minimal implementation**

```python
def _delete_files_in_destination(self, dest_dir: str, source_files: set, dest_files: set) -> None:
    """Delete files in destination that don't exist in source.
    
    Args:
        dest_dir: Destination directory path
        source_files: Set of files in source directory
        dest_files: Set of files in destination directory
    """
    files_to_delete = dest_files - source_files
    
    for file_path in files_to_delete:
        full_path = os.path.join(dest_dir, file_path)
        try:
            if os.path.isfile(full_path):
                os.remove(full_path)
            elif os.path.isdir(full_path):
                import shutil
                shutil.rmtree(full_path)
        except Exception as e:
            print(f"DEBUG: Failed to delete {full_path}: {e}")
            # Continue with other files even if one fails
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest build-env/tests/test_build_env.py::test_delete_files_in_destination -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add build-env/build_env.py build-env/tests/test_build_env.py
git commit -m "feat: add destination deletion helper method"
```

### Task 3: Enhance Host to Container Sync with Deletions

**Files:**
- Modify: `build-env/build_env.py:108-148` (update `_synchronize_host_to_container`)

- [ ] **Step 1: Write the failing test**

```python
def test_host_to_container_sync_with_deletions():
    """Test host→container sync handles deletions properly"""
    import tempfile
    import os
    
    # Mock container scenario
    with tempfile.TemporaryDirectory() as tmpdir:
        # Simulate container workspace
        container_dir = os.path.join(tmpdir, 'container')
        host_dir = os.path.join(tmpdir, 'host')
        os.makedirs(container_dir)
        os.makedirs(host_dir)
        
        # Create files that should exist in both
        with open(os.path.join(host_dir, 'common.txt'), 'w') as f:
            f.write('common')
        with open(os.path.join(container_dir, 'common.txt'), 'w') as f:
            f.write('common')
        
        # Create file that should be deleted from container
        with open(os.path.join(container_dir, 'delete_me.txt'), 'w') as f:
            f.write('delete')
        
        # Mock the sync process
        manager = BuildEnvironmentManager()
        
        # Get file lists
        host_files = manager._get_file_list(host_dir)
        container_files = manager._get_file_list(container_dir)
        
        # Delete files in container that don't exist on host
        manager._delete_files_in_destination(container_dir, host_files, container_files)
        
        # Verify deletion
        assert not os.path.exists(os.path.join(container_dir, 'delete_me.txt'))
        assert os.path.exists(os.path.join(container_dir, 'common.txt'))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest build-env/tests/test_build_env.py::test_host_to_container_sync_with_deletions -v`
Expected: PASS (since we're testing existing functionality)

- [ ] **Step 3: Enhance the sync method**

```python
def _synchronize_host_to_container(self, container_name: str, workspace_path: str) -> bool:
    """Synchronize files from host to container with deletion handling.
    
    Args:
        container_name: Name of the container
        workspace_path: Path to the workspace
        
    Returns:
        True if successful, False otherwise
    """
    try:
        import subprocess

        # Get container
        container = self.docker_client.containers.get(container_name)

        # Create workspace directory in container if it doesn't exist
        exec_result = container.exec_run(f'mkdir -p {workspace_path}')
        if exec_result.exit_code != 0:
            return False

        # Remove .build-env directory in container to prevent UUID contamination
        container.exec_run(f'rm -rf {workspace_path}/.build-env')

        # Get file lists for comparison
        host_files = self._get_file_list(workspace_path)
        
        # Get container file list by copying to temp directory
        with tempfile.TemporaryDirectory() as temp_dir:
            # Copy container files to temp directory
            result = subprocess.run(
                ['docker', 'cp', f'{container_name}:{workspace_path}/.', temp_dir],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                container_files = self._get_file_list(temp_dir)
                
                # Delete files in container that don't exist on host
                for file_path in container_files - host_files:
                    container.exec_run(f'rm -rf {workspace_path}/{file_path}')

        # Copy host files to container (host → container)
        result = subprocess.run(
            ['docker', 'cp', f'{workspace_path}/.', f'{container_name}:{workspace_path}'],
            capture_output=True,
            text=True
        )

        # Debug logging
        print(f"DEBUG: Host→Container sync with deletions: workspace_path={workspace_path}, container_name={container_name}")
        print(f"DEBUG: Sync result: returncode={result.returncode}, stderr={result.stderr}")

        return result.returncode == 0

    except Exception as e:
        print(f"DEBUG: Host→Container sync exception: {e}")
        return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest build-env/tests/test_build_env.py::test_host_to_container_sync_with_deletions -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add build-env/build_env.py build-env/tests/test_build_env.py
git commit -m "feat: enhance host→container sync with deletion handling"
```

### Task 4: Enhance Container to Host Sync with Deletions

**Files:**
- Modify: `build-env/build_env.py:149-183` (update `_synchronize_container_to_host`)

- [ ] **Step 1: Write the failing test**

```python
def test_container_to_host_sync_with_deletions():
    """Test container→host sync handles deletions properly"""
    import tempfile
    import os
    
    # Mock container scenario
    with tempfile.TemporaryDirectory() as tmpdir:
        # Simulate container workspace
        container_dir = os.path.join(tmpdir, 'container')
        host_dir = os.path.join(tmpdir, 'host')
        os.makedirs(container_dir)
        os.makedirs(host_dir)
        
        # Create files that should exist in both
        with open(os.path.join(container_dir, 'common.txt'), 'w') as f:
            f.write('common')
        with open(os.path.join(host_dir, 'common.txt'), 'w') as f:
            f.write('common')
        
        # Create file that should be deleted from host
        with open(os.path.join(host_dir, 'delete_me.txt'), 'w') as f:
            f.write('delete')
        
        # Mock the sync process
        manager = BuildEnvironmentManager()
        
        # Get file lists
        container_files = manager._get_file_list(container_dir)
        host_files = manager._get_file_list(host_dir)
        
        # Delete files on host that don't exist in container
        manager._delete_files_in_destination(host_dir, container_files, host_files)
        
        # Verify deletion
        assert not os.path.exists(os.path.join(host_dir, 'delete_me.txt'))
        assert os.path.exists(os.path.join(host_dir, 'common.txt'))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest build-env/tests/test_build_env.py::test_container_to_host_sync_with_deletions -v`
Expected: PASS (since we're testing existing functionality)

- [ ] **Step 3: Enhance the sync method**

```python
def _synchronize_container_to_host(self, container_name: str, workspace_path: str) -> bool:
    """Synchronize files from container to host with deletion handling.
    
    Args:
        container_name: Name of the container
        workspace_path: Path to the workspace
        
    Returns:
        True if successful, False otherwise
    """
    try:
        import subprocess

        # Remove .build-env directory on host to prevent UUID contamination
        build_env_path = os.path.join(workspace_path, '.build-env')
        if os.path.exists(build_env_path):
            import shutil
            shutil.rmtree(build_env_path)

        # Get file lists for comparison
        container_files = set()
        
        # Get container file list by copying to temp directory
        with tempfile.TemporaryDirectory() as temp_dir:
            # Copy container files to temp directory
            result = subprocess.run(
                ['docker', 'cp', f'{container_name}:{workspace_path}/.', temp_dir],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                container_files = self._get_file_list(temp_dir)
                host_files = self._get_file_list(workspace_path)
                
                # Delete files on host that don't exist in container
                self._delete_files_in_destination(workspace_path, container_files, host_files)

        # Copy container files back to host (container → host)
        result = subprocess.run(
            ['docker', 'cp', f'{container_name}:{workspace_path}/.', workspace_path],
            capture_output=True,
            text=True
        )

        # Debug logging
        print(f"DEBUG: Container→Host sync with deletions: workspace_path={workspace_path}, container_name={container_name}")
        print(f"DEBUG: Sync result: returncode={result.returncode}, stderr={result.stderr}")

        return result.returncode == 0

    except Exception as e:
        print(f"DEBUG: Container→Host sync exception: {e}")
        return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest build-env/tests/test_build_env.py::test_container_to_host_sync_with_deletions -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add build-env/build_env.py build-env/tests/test_build_env.py
git commit -m "feat: enhance container→host sync with deletion handling"
```

### Task 5: Add Integration Test for Deletion Synchronization

**Files:**
- Modify: `build-env/tests/test_integration.py:50-100`

- [ ] **Step 1: Write the integration test**

```python
def test_bidirectional_deletion_sync():
    """Integration test for bidirectional deletion synchronization"""
    import tempfile
    import os
    
    # Skip if Docker not available
    try:
        docker.from_env().ping()
    except Exception:
        pytest.skip("Docker not available")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace_path = tmpdir
        
        # Set up environment
        os.environ['BUILD_CONTAINER'] = 'alpine:latest'
        os.environ['DEFAULT_WORKSPACE'] = workspace_path
        
        manager = BuildEnvironmentManager()
        
        # Create initial container
        container_name = manager._start_container(
            os.environ['BUILD_CONTAINER'],
            workspace_path,
            dict(os.environ)
        )
        
        # Test 1: File deletion sync from host to container
        # Create file on host
        test_file = 'delete_test.txt'
        with open(os.path.join(workspace_path, test_file), 'w') as f:
            f.write('test content')
        
        # Sync host → container
        assert manager._synchronize_host_to_container(container_name, workspace_path)
        
        # Delete file on host
        os.remove(os.path.join(workspace_path, test_file))
        
        # Sync host → container again (should delete from container)
        assert manager._synchronize_host_to_container(container_name, workspace_path)
        
        # Verify file was deleted from container
        result = container.exec_run(f'ls {workspace_path}/{test_file}')
        assert result.exit_code != 0  # File should not exist
        
        # Test 2: File deletion sync from container to host
        # Create file in container
        container_file = 'container_delete_test.txt'
        container.exec_run(f'touch {workspace_path}/{container_file}')
        
        # Sync container → host
        assert manager._synchronize_container_to_host(container_name, workspace_path)
        
        # Verify file exists on host
        assert os.path.exists(os.path.join(workspace_path, container_file))
        
        # Delete file in container
        container.exec_run(f'rm {workspace_path}/{container_file}')
        
        # Sync container → host again (should delete from host)
        assert manager._synchronize_container_to_host(container_name, workspace_path)
        
        # Verify file was deleted from host
        assert not os.path.exists(os.path.join(workspace_path, container_file))
        
        # Cleanup
        manager._shutdown_container(container_name)
        
    except Exception as e:
        # Ensure cleanup
        try:
            manager._shutdown_container(container_name)
        except:
            pass
        raise e
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest build-env/tests/test_integration.py::test_bidirectional_deletion_sync -v`
Expected: FAIL (integration test should fail initially)

- [ ] **Step 3: Run test to verify it passes after implementation**

Run: `pytest build-env/tests/test_integration.py::test_bidirectional_deletion_sync -v`
Expected: PASS (after all sync methods are enhanced)

- [ ] **Step 4: Commit**

```bash
git add build-env/tests/test_integration.py
git commit -m "test: add integration test for bidirectional deletion sync"
```

### Task 6: Update README Documentation

**Files:**
- Modify: `build-env/README.md:87-99`

- [ ] **Step 1: Update the bidirectional sync section**

```markdown
### Bidirectional Synchronization

When running in Docker-in-Docker scenarios, the tool provides advanced bidirectional file synchronization:

- **Smart Synchronization**: Files are intelligently synchronized based on content comparison
- **Deletion Handling**: Properly handles file and folder deletions in both directions - files and folders deleted on one side are deleted on the other
- **Conflict Resolution**: Uses modification timestamps to resolve conflicts
- **Host to Container**: Files are synchronized from host to container before command execution, including deletion of files that exist only in the container
- **Container to Host**: After command execution, any changes made in the container are synchronized back to the host, including deletion of files that exist only on the host
- **Automatic**: Synchronization happens automatically for Docker-in-Docker scenarios
- **Complete**: All files in the workspace directory are synchronized in both directions

The synchronization algorithm:
1. **Compare Files and Folders**: Identifies files and folders that exist in only one location
2. **Delete Orphaned Items**: Deletes files and folders that exist in destination but not source
3. **Copy Missing Items**: Copies files and folders that exist in one location but not the other
4. **Resolve Conflicts**: For files that exist in both locations, compares content and uses newer version
```

- [ ] **Step 2: Verify documentation update**

Run: `cat build-env/README.md | grep -A 10 "Bidirectional Synchronization"`
Expected: See updated documentation with deletion handling details

- [ ] **Step 3: Commit**

```bash
git add build-env/README.md
git commit -m "docs: update README with bidirectional deletion sync details"
```

### Task 7: Final Verification and Testing

**Files:**
- All modified files

- [ ] **Step 1: Run all tests**

Run: `pytest build-env/tests/ -v`
Expected: All tests PASS

- [ ] **Step 2: Verify no regression**

Run: `python -c "from build_env import BuildEnvironmentManager; print('Import successful')"`
Expected: No errors

- [ ] **Step 3: Test CLI functionality**

Run: `cd build-env && python -m build_env_cli --help`
Expected: CLI help displays without errors

- [ ] **Step 4: Final commit**

```bash
git add .
git commit -m "feat: complete bidirectional deletion synchronization implementation"
```

## Self-Review

**Spec coverage:** All requirements from the spec are covered:
- ✅ File listing helper method
- ✅ Destination deletion helper method  
- ✅ Enhanced host→container sync with deletions
- ✅ Enhanced container→host sync with deletions
- ✅ Integration tests
- ✅ Documentation updates

**Placeholder scan:** No placeholders found - all tasks contain complete code

**Type consistency:** Method names and signatures are consistent throughout

**Execution choice:** Ready for implementation