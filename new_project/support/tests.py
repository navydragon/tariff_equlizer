import json
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

from support.domain.dto import CreateTaskDTO
from support.domain.services import AttachmentService, CommentService, TaskService
from support.models import Task, TaskComment

User = get_user_model()


class SupportTaskTests(TestCase):
    def setUp(self):
        self.author = User.objects.create_user(
            login="author",
            password="pass12345",
            email="author@test.com",
            first_name="Автор",
            last_name="Тестов",
        )
        self.other = User.objects.create_user(
            login="other",
            password="pass12345",
            email="other@test.com",
            first_name="Другой",
            last_name="Пользователь",
        )
        self.staff = User.objects.create_user(
            login="staff",
            password="pass12345",
            email="staff@test.com",
            first_name="Стафф",
            last_name="Админ",
            is_staff=True,
        )
        self.client = Client()
        self.service = TaskService()

    def test_create_task(self):
        task, errors = self.service.create_task(
            self.author,
            CreateTaskDTO(title="Тестовая задача", description="Описание"),
        )
        self.assertEqual(errors, [])
        self.assertIsNotNone(task)
        self.assertEqual(task.title, "Тестовая задача")
        self.assertEqual(Task.objects.count(), 1)

    def test_create_task_requires_title(self):
        task, errors = self.service.create_task(self.author, CreateTaskDTO(title="  "))
        self.assertIsNone(task)
        self.assertIn("Заголовок обязателен", errors)

    def test_add_comment(self):
        task, _ = self.service.create_task(self.author, CreateTaskDTO(title="Задача"))
        comment_service = CommentService()
        comment, errors = comment_service.add_comment(task.id, self.other, "Комментарий")
        self.assertEqual(errors, [])
        self.assertEqual(comment["body"], "Комментарий")
        self.assertEqual(TaskComment.objects.count(), 1)

    def test_update_status(self):
        task, _ = self.service.create_task(self.author, CreateTaskDTO(title="Задача"))
        updated, errors = self.service.update_status(task.id, self.other, "in_progress")
        self.assertEqual(errors, [])
        self.assertEqual(updated.status, "in_progress")

    def test_delete_task_by_author(self):
        task, _ = self.service.create_task(self.author, CreateTaskDTO(title="Задача"))
        errors = self.service.delete_task(task.id, self.author)
        self.assertEqual(errors, [])
        self.assertEqual(Task.objects.count(), 0)

    def test_delete_task_denied_for_other(self):
        task, _ = self.service.create_task(self.author, CreateTaskDTO(title="Задача"))
        errors = self.service.delete_task(task.id, self.other)
        self.assertIn("Нет прав на удаление", errors[0])
        self.assertEqual(Task.objects.count(), 1)

    def test_delete_task_allowed_for_staff(self):
        task, _ = self.service.create_task(self.author, CreateTaskDTO(title="Задача"))
        errors = self.service.delete_task(task.id, self.staff)
        self.assertEqual(errors, [])
        self.assertEqual(Task.objects.count(), 0)

    def test_upload_attachment(self):
        task, _ = self.service.create_task(self.author, CreateTaskDTO(title="Задача"))
        uploaded = SimpleUploadedFile("test.txt", b"hello", content_type="text/plain")
        attachment_service = AttachmentService()
        result, errors = attachment_service.upload(task.id, self.author, uploaded)
        self.assertEqual(errors, [])
        self.assertEqual(result["original_name"], "test.txt")

    def test_upload_attachment_rejects_large_file(self):
        task, _ = self.service.create_task(self.author, CreateTaskDTO(title="Задача"))
        big_content = BytesIO(b"x" * (11 * 1024 * 1024))
        uploaded = SimpleUploadedFile("big.bin", big_content.read())
        attachment_service = AttachmentService()
        result, errors = attachment_service.upload(task.id, self.author, uploaded)
        self.assertIsNone(result)
        self.assertTrue(any("превышает" in e for e in errors))

    def test_task_list_api_requires_login(self):
        response = self.client.get(reverse("support:api_task_list"))
        self.assertEqual(response.status_code, 302)

    def test_task_list_api_authenticated(self):
        self.service.create_task(self.author, CreateTaskDTO(title="Задача 1"))
        self.client.login(login="author", password="pass12345")
        response = self.client.get(reverse("support:api_task_list"))
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data["success"])
        self.assertEqual(len(data["tasks"]), 1)

    def test_create_task_via_api(self):
        self.client.login(login="author", password="pass12345")
        response = self.client.post(
            reverse("support:api_task_list"),
            data=json.dumps({"title": "API задача", "description": "Тест"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data["success"])
        self.assertEqual(data["task"]["title"], "API задача")

    def test_task_list_page(self):
        self.client.login(login="author", password="pass12345")
        response = self.client.get(reverse("support:task_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Управление задачами")
