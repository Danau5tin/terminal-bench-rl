"""File manager for handling file operations in the Docker container."""

import logging
import os
from typing import List, Optional, Tuple

from src.agent_core.env_components.command_executor import CommandExecutor

logger = logging.getLogger(__name__)


class FileManager:
    """Manages file operations within Docker container via bash commands."""
    
    def __init__(self, executor: CommandExecutor):
        self.executor = executor
    
    async def _run_command(self, cmd: str, timeout: int = 30) -> Tuple[str, int]:
        """Run a command using the executor and return (output, exit_code)."""
        return await self.executor.execute(cmd, timeout=timeout)
    
    async def read_file(self, file_path: str, offset: Optional[int] = None, 
                       limit: Optional[int] = None) -> Tuple[str, bool]:
        """Read file contents with optional offset and limit."""
        if offset is not None and limit is not None:
            # Read specific lines
            cmd = f"tail -n +{offset} '{file_path}' 2>&1 | head -n {limit} | nl -ba -v {offset}"
        elif limit is not None:
            # Read first N lines
            cmd = f"head -n {limit} '{file_path}' 2>&1 | nl -ba"
        else:
            # Read entire file with line numbers
            cmd = f"nl -ba '{file_path}' 2>&1"
        
        logger.debug(f"[FileManager] Reading file with command: {cmd}")
        output, code = await self._run_command(cmd)
        
        if "No such file or directory" in output or "cannot open" in output:
            return f"File not found: {file_path}", True
        
        if code != 0 and output:
            return f"Error reading file: {output}", True
        
        return output, False
    
    async def write_file(self, file_path: str, content: str) -> Tuple[str, bool]:
        """Write content to a file."""
        # Create directory if it doesn't exist
        dir_path = os.path.dirname(file_path)
        if dir_path:
            mkdir_cmd = f"mkdir -p '{dir_path}'"
            await self._run_command(mkdir_cmd)
        
        # Use printf with base64 encoding to handle all special characters safely
        # This avoids issues with heredocs and multi-line content in tmux
        import base64
        encoded_content = base64.b64encode(content.encode('utf-8')).decode('ascii')
        
        # Write the file by decoding base64 content
        write_cmd = f"echo '{encoded_content}' | base64 -d > '{file_path}'"
        
        output, code = await self._run_command(write_cmd)
        
        if code != 0:
            return f"Error writing file: {output}", True
        
        return f"Successfully wrote to {file_path}", False
    
    async def edit_file(self, file_path: str, old_string: str, new_string: str, 
                       replace_all: bool = False) -> Tuple[str, bool]:
        """Edit file by replacing strings."""
        # Try to create a backup first - this will fail if file doesn't exist
        backup_cmd = f"cp '{file_path}' '{file_path}.bak' 2>&1"
        output, code = await self._run_command(backup_cmd)
        
        if "No such file or directory" in output or code != 0:
            return f"File not found: {file_path}", True
        
        # Escape special characters for sed
        def escape_for_sed(s: str) -> str:
            # Escape special regex characters
            s = s.replace('\\', '\\\\')
            s = s.replace('/', '\\/')
            s = s.replace('.', '\\.')
            s = s.replace('*', '\\*')
            s = s.replace('[', '\\[')
            s = s.replace(']', '\\]')
            s = s.replace('^', '\\^')
            s = s.replace('$', '\\$')
            s = s.replace('&', '\\&')
            return s
        
        escaped_old = escape_for_sed(old_string)
        escaped_new = escape_for_sed(new_string)
        
        # Create backup
        backup_cmd = f"cp '{file_path}' '{file_path}.bak'"
        await self._run_command(backup_cmd)
        
        # Perform replacement
        if replace_all:
            sed_cmd = f"sed -i 's/{escaped_old}/{escaped_new}/g' '{file_path}'"
        else:
            sed_cmd = f"sed -i '0,/{escaped_old}/s//{escaped_new}/' '{file_path}'"
        
        output, code = await self._run_command(sed_cmd)
        
        # Clean up backup
        cleanup_cmd = f"rm -f '{file_path}.bak'"
        await self._run_command(cleanup_cmd)
        
        if code != 0:
            return f"Error editing file: {output}", True
        
        return f"Successfully replaced {'all occurrences' if replace_all else 'first occurrence'} in {file_path}", False
    
    async def multi_edit_file(self, file_path: str, edits: List[Tuple[str, str, bool]]) -> Tuple[str, bool]:
        """Perform multiple edits on a file."""
        results = []
        
        for i, (old_string, new_string, replace_all) in enumerate(edits):
            result, is_error = await self.edit_file(file_path, old_string, new_string, replace_all)
            
            if is_error and "No matches found" not in result:
                return f"Error on edit {i+1}: {result}", True
            
            results.append(f"Edit {i+1}: {result}")
        
        return "\n".join(results), False
    
    async def get_metadata(self, file_paths: List[str]) -> Tuple[str, bool]:
        """Get metadata for multiple files."""
        results = []
        
        for file_path in file_paths[:10]:  # Limit to 10 files
            # Check if file exists and get stats
            stat_cmd = f"""
            if [ -e '{file_path}' ]; then
                stat -c '%s %Y %U:%G %a' '{file_path}' 2>/dev/null || stat -f '%z %m %Su:%Sg %Lp' '{file_path}'
                echo -n ' '
                file -b '{file_path}' 2>/dev/null || echo 'unknown'
            else
                echo 'not_found'
            fi
            """
            
            output, _ = await self._run_command(stat_cmd)
            
            if "not_found" in output:
                results.append(f"{file_path}: Not found")
            else:
                parts = output.strip().split(maxsplit=4)
                if len(parts) >= 5:
                    size, mtime, owner, perms, filetype = parts[0], parts[1], parts[2], parts[3], ' '.join(parts[4:])
                    results.append(f"{file_path}:\n  Size: {size} bytes\n  Type: {filetype}\n  Owner: {owner}\n  Permissions: {perms}")
                else:
                    results.append(f"{file_path}: Unable to get metadata")
        
        return "\n\n".join(results), False