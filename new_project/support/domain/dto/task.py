from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class CreateTaskDTO:
    title: str
    description: str = ""
    priority: str = "medium"
    task_type: str = "question"
    deadline: Optional[datetime] = None
    assignee_id: Optional[int] = None
    scenario_id: Optional[int] = None
    tag_ids: list[int] = field(default_factory=list)


@dataclass
class UpdateTaskDTO:
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    task_type: Optional[str] = None
    deadline: Optional[datetime] = None
    assignee_id: Optional[int] = None
    scenario_id: Optional[int] = None
    tag_ids: Optional[list[int]] = None
    clear_deadline: bool = False
    clear_assignee: bool = False
    clear_scenario: bool = False


@dataclass
class TaskFiltersDTO:
    scope: str = "all"
    status: Optional[str] = None
    priority: Optional[str] = None
    task_type: Optional[str] = None
    author_id: Optional[int] = None
    assignee_id: Optional[int] = None
    tag_id: Optional[int] = None
    search: str = ""
    overdue_only: bool = False
    unassigned_only: bool = False


@dataclass
class TaskListDTO:
    id: int
    title: str
    status: str
    status_label: str
    priority: str
    priority_label: str
    task_type: str
    task_type_label: str
    deadline: Optional[str]
    is_overdue: bool
    author_id: int
    author_name: str
    assignee_id: Optional[int]
    assignee_name: Optional[str]
    scenario_id: Optional[int]
    scenario_name: Optional[str]
    tags: list[dict]
    comments_count: int
    attachments_count: int
    created_at: str
    updated_at: str


@dataclass
class TaskCommentDTO:
    id: int
    author_id: int
    author_name: str
    body: str
    created_at: str
    updated_at: str


@dataclass
class TaskDetailDTO:
    id: int
    title: str
    description: str
    status: str
    status_label: str
    priority: str
    priority_label: str
    task_type: str
    task_type_label: str
    deadline: Optional[str]
    is_overdue: bool
    author_id: int
    author_name: str
    assignee_id: Optional[int]
    assignee_name: Optional[str]
    scenario_id: Optional[int]
    scenario_name: Optional[str]
    tags: list[dict]
    comments: list[TaskCommentDTO]
    attachments: list[dict]
    activities: list[dict]
    watchers_count: int
    is_watching: bool
    created_at: str
    updated_at: str
    closed_at: Optional[str]
