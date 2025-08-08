"""Action handler for executing parsed actions in the RLLM environment."""

import logging
from typing import Dict, Callable, Tuple, Optional

from src.agent_core.env_components.actions import (
    Action,
    AddTodoAction,
    CompleteTodoAction,
    DeleteTodoAction,
    ViewAllTodosAction,
    BatchTodoAction,
    AddNoteAction,
    ViewAllNotesAction,
    ReadAction,
    WriteAction,
    EditAction,
    MultiEditAction,
    GrepAction,
    GlobAction,
    LSAction,
    FileMetadataAction,
    BashAction,
    FinishAction,
)
from src.agent_core.env_components.state_managers import TodoManager, ScratchpadManager
from src.agent_core.env_components.file_manager import FileManager
from src.agent_core.env_components.search_manager import SearchManager
from src.agent_core.env_components.command_executor import CommandExecutor

logger = logging.getLogger(__name__)


def format_tool_output(tool_name: str, content: str) -> str:
    """Format tool output in XML format.
    
    Args:
        tool_name: Name of the tool (e.g., 'todo', 'file', 'search')
        content: The raw content to wrap
        
    Returns:
        XML-formatted output string
    """
    tag_name = f"{tool_name}_output"
    return f"<{tag_name}>\n{content}\n</{tag_name}>"


class ActionHandler:
    """Handles execution of different action types."""
    
    @staticmethod
    def truncate_content(content: str, max_length: int = 15) -> str:
        """Truncate content for display to reduce tokens."""
        return content[:max_length] + "..." if len(content) > max_length else content
    
    def __init__(
        self,
        executor: CommandExecutor,
        todo_manager: Optional[TodoManager] = None,
        scratchpad_manager: Optional[ScratchpadManager] = None,
    ):
        self.executor = executor
        self.todo_manager = todo_manager or TodoManager()
        self.scratchpad_manager = scratchpad_manager or ScratchpadManager()
        self.file_manager = FileManager(executor)
        self.search_manager = SearchManager(executor)
        
        # Map action types to handler methods
        self._handlers: Dict[type, Callable] = {
            AddTodoAction: self._handle_add_todo,
            CompleteTodoAction: self._handle_complete_todo,
            DeleteTodoAction: self._handle_delete_todo,
            ViewAllTodosAction: self._handle_view_all_todos,
            BatchTodoAction: self._handle_batch_todo,
            AddNoteAction: self._handle_add_note,
            ViewAllNotesAction: self._handle_view_all_notes,
            ReadAction: self._handle_read_file,
            WriteAction: self._handle_write_file,
            EditAction: self._handle_edit_file,
            MultiEditAction: self._handle_multi_edit_file,
            GrepAction: self._handle_grep,
            GlobAction: self._handle_glob,
            LSAction: self._handle_ls,
            FileMetadataAction: self._handle_file_metadata,
            BashAction: self._handle_bash,
            FinishAction: self._handle_finish,
        }
    
    async def handle_action(self, action: Action) -> Tuple[str, bool]:
        """Handle an action and return (response, is_error)."""
        handler = self._handlers.get(type(action))
        if handler:
            return await handler(action)
        content = f"[ERROR] Unknown action type: {type(action).__name__}"
        return format_tool_output("unknown", content), True
    
    async def _handle_add_todo(self, action: AddTodoAction) -> Tuple[str, bool]:
        """Handle adding a new todo."""
        if not action.content:
            error_msg = "[ERROR] Cannot add empty todo"
            # Always include todo list on errors
            content = f"{error_msg}\n\n{self.todo_manager.view_all()}"
            return format_tool_output("todo", content), True
        
        task_id = self.todo_manager.add_task(action.content)
        truncated_content = self.truncate_content(action.content)
        response = f"Added todo [{task_id}]: {truncated_content}"
        
        # Include todo list if requested
        if action.view_all:
            response += f"\n\n{self.todo_manager.view_all()}"
        
        return format_tool_output("todo", response), False
    
    async def _handle_complete_todo(self, action: CompleteTodoAction) -> Tuple[str, bool]:
        """Handle completing a todo."""
        if action.task_id < 1:
            error_msg = f"[ERROR] Invalid task_id: {action.task_id}"
            content = f"{error_msg}\n\n{self.todo_manager.view_all()}"
            return format_tool_output("todo", content), True
        
        task = self.todo_manager.get_task(action.task_id)
        if not task:
            error_msg = f"[ERROR] Task {action.task_id} not found"
            content = f"{error_msg}\n\n{self.todo_manager.view_all()}"
            return format_tool_output("todo", content), True
        
        if task["status"] == "completed":
            response = f"Task {action.task_id} is already completed"
            if action.view_all:
                response += f"\n\n{self.todo_manager.view_all()}"
            return format_tool_output("todo", response), False
        
        success = self.todo_manager.complete_task(action.task_id)
        if success:
            response = f"Completed task [{action.task_id}]: {task['content']}"
            if action.view_all:
                response += f"\n\n{self.todo_manager.view_all()}"
            return format_tool_output("todo", response), False
        else:
            error_msg = f"[ERROR] Failed to complete task {action.task_id}"
            content = f"{error_msg}\n\n{self.todo_manager.view_all()}"
            return format_tool_output("todo", content), True
    
    async def _handle_delete_todo(self, action: DeleteTodoAction) -> Tuple[str, bool]:
        """Handle deleting a todo."""
        if action.task_id < 1:
            error_msg = f"[ERROR] Invalid task_id: {action.task_id}"
            content = f"{error_msg}\n\n{self.todo_manager.view_all()}"
            return format_tool_output("todo", content), True
        
        task = self.todo_manager.get_task(action.task_id)
        if not task:
            error_msg = f"[ERROR] Task {action.task_id} not found"
            content = f"{error_msg}\n\n{self.todo_manager.view_all()}"
            return format_tool_output("todo", content), True
        
        success = self.todo_manager.delete_task(action.task_id)
        if success:
            response = f"Deleted task [{action.task_id}]: {task['content']}"
            if action.view_all:
                response += f"\n\n{self.todo_manager.view_all()}"
            return format_tool_output("todo", response), False
        else:
            error_msg = f"[ERROR] Failed to delete task {action.task_id}"
            content = f"{error_msg}\n\n{self.todo_manager.view_all()}"
            return format_tool_output("todo", content), True
    
    async def _handle_view_all_todos(self, action: ViewAllTodosAction) -> Tuple[str, bool]:
        """Handle viewing all todos."""
        return format_tool_output("todo", self.todo_manager.view_all()), False
    
    async def _handle_batch_todo(self, action: BatchTodoAction) -> Tuple[str, bool]:
        """Handle batch todo operations."""
        results = []
        has_error = False
        
        for op in action.operations:
            if op.action == "add":
                task_id = self.todo_manager.add_task(op.content)
                truncated_content = self.truncate_content(op.content)
                results.append(f"Added todo [{task_id}]: {truncated_content}")
            
            elif op.action == "complete":
                task = self.todo_manager.get_task(op.task_id)
                if not task:
                    results.append(f"[ERROR] Task {op.task_id} not found")
                    has_error = True
                elif task["status"] == "completed":
                    results.append(f"Task {op.task_id} is already completed")
                else:
                    self.todo_manager.complete_task(op.task_id)
                    truncated_content = self.truncate_content(task['content'])
                    results.append(f"Completed task [{op.task_id}]: {truncated_content}")
            
            elif op.action == "delete":
                task = self.todo_manager.get_task(op.task_id)
                if not task:
                    results.append(f"[ERROR] Task {op.task_id} not found")
                    has_error = True
                else:
                    self.todo_manager.delete_task(op.task_id)
                    truncated_content = self.truncate_content(task['content'])
                    results.append(f"Deleted task [{op.task_id}]: {truncated_content}")
            
            elif op.action == "view_all":
                # This is handled after all operations
                pass
        
        # Join results
        response = "\n".join(results)
        
        # Add todo list if requested
        if action.view_all:
            response += f"\n\n{self.todo_manager.view_all()}"
        
        return format_tool_output("todo", response), has_error
    
    async def _handle_add_note(self, action: AddNoteAction) -> Tuple[str, bool]:
        """Handle adding a note to scratchpad."""
        if not action.content:
            return format_tool_output("scratchpad", "[ERROR] Cannot add empty note"), True
        
        note_idx = self.scratchpad_manager.add_note(action.content)
        response = f"Added note {note_idx + 1} to scratchpad"
        return format_tool_output("scratchpad", response), False
    
    async def _handle_view_all_notes(self, action: ViewAllNotesAction) -> Tuple[str, bool]:
        """Handle viewing all notes."""
        return format_tool_output("scratchpad", self.scratchpad_manager.view_all()), False
    
    async def _handle_read_file(self, action: ReadAction) -> Tuple[str, bool]:
        """Handle reading a file."""
        content, is_error = await self.file_manager.read_file(
            action.file_path, action.offset, action.limit
        )
        return format_tool_output("file", content), is_error
    
    async def _handle_write_file(self, action: WriteAction) -> Tuple[str, bool]:
        """Handle writing a file."""
        content, is_error = await self.file_manager.write_file(
            action.file_path, action.content
        )
        return format_tool_output("file", content), is_error
    
    async def _handle_edit_file(self, action: EditAction) -> Tuple[str, bool]:
        """Handle editing a file."""
        content, is_error = await self.file_manager.edit_file(
            action.file_path, action.old_string, action.new_string, action.replace_all
        )
        return format_tool_output("file", content), is_error
    
    async def _handle_multi_edit_file(self, action: MultiEditAction) -> Tuple[str, bool]:
        """Handle multiple edits to a file."""
        edits = [(e.old_string, e.new_string, e.replace_all) for e in action.edits]
        content, is_error = await self.file_manager.multi_edit_file(
            action.file_path, edits
        )
        return format_tool_output("file", content), is_error
    
    async def _handle_grep(self, action: GrepAction) -> Tuple[str, bool]:
        """Handle grep search."""
        content, is_error = await self.search_manager.grep(
            action.pattern, action.path, action.include
        )
        return format_tool_output("search", content), is_error
    
    async def _handle_glob(self, action: GlobAction) -> Tuple[str, bool]:
        """Handle glob search."""
        content, is_error = await self.search_manager.glob(
            action.pattern, action.path
        )
        return format_tool_output("search", content), is_error
    
    async def _handle_ls(self, action: LSAction) -> Tuple[str, bool]:
        """Handle ls command."""
        content, is_error = await self.search_manager.ls(
            action.path, action.ignore
        )
        return format_tool_output("search", content), is_error
    
    async def _handle_file_metadata(self, action: FileMetadataAction) -> Tuple[str, bool]:
        """Handle file metadata request."""
        content, is_error = await self.file_manager.get_metadata(action.file_paths)
        return format_tool_output("file", content), is_error
    
    async def _handle_bash(self, action: BashAction) -> Tuple[str, bool]:
        """Handle bash command execution."""
        try:
            if action.block:
                output, exit_code = await self.executor.execute(
                    action.cmd, 
                    timeout=action.timeout_secs
                )
            else:
                # Non-blocking execution
                await self.executor.execute_background(action.cmd)
                output = "Command started in background"
                exit_code = 0
            
            is_error = exit_code != 0
            return format_tool_output("bash", output), is_error
            
        except Exception as e:
            error_msg = f"Error executing command: {str(e)}"
            return format_tool_output("bash", error_msg), True
    
    async def _handle_finish(self, action: FinishAction) -> Tuple[str, bool]:
        """Handle finish action."""
        response = f"Task marked as complete: {action.message}"
        return format_tool_output("finish", response), False
    