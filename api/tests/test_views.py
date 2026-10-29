from uuid import uuid4

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from api.models import Category, Company


class CategoryViewTests(APITestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Acme")
        self.other_company = Company.objects.create(name="Other company")
        self.parent_category = Category.objects.create(company=self.company, name="Parent")
        self.category = Category.objects.create(
            company=self.company,
            name="Current",
            parent_category=self.parent_category,
        )
        self.list_url = reverse("category-list")

    def test_list(self):
        other_category = Category.objects.create(company=self.other_company, name="Current")

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            {item["id"] for item in response.data},
            {str(self.parent_category.id), str(self.category.id), str(other_category.id)},
        )

    def test_retrieve(self):
        detail_url = reverse("category-detail", args=[self.category.id])

        response = self.client.get(detail_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], str(self.category.id))
        self.assertEqual(response.data["company"], str(self.company.id))
        self.assertEqual(response.data["name"], self.category.name)
        self.assertEqual(response.data["parent_category"], str(self.parent_category.id))
        self.assertIn("created_at", response.data)
        self.assertIn("updated_at", response.data)

        missing_url = reverse("category-detail", args=[uuid4()])
        self.assertEqual(self.client.get(missing_url).status_code, status.HTTP_404_NOT_FOUND)

    def test_create(self):
        payload = {
            "company": str(self.company.id),
            "name": "Child",
            "parent_category": str(self.parent_category.id),
        }

        response = self.client.post(self.list_url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["company"], str(self.company.id))
        self.assertEqual(response.data["name"], payload["name"])
        self.assertEqual(response.data["parent_category"], str(self.parent_category.id))
        self.assertTrue(Category.objects.filter(id=response.data["id"], **payload).exists())

    def test_create_rejects_invalid_fields(self):
        invalid_payloads = [
            ({"name": "Missing company"}, "company"),
            ({"company": str(self.company.id), "name": ""}, "name"),
            ({"company": str(self.company.id), "name": "x" * 256}, "name"),
            ({"company": str(uuid4()), "name": "Unknown company"}, "company"),
            (
                {
                    "company": str(self.company.id),
                    "name": "Unknown parent",
                    "parent_category": str(uuid4()),
                },
                "parent_category",
            ),
        ]

        for payload, error_field in invalid_payloads:
            with self.subTest(error_field=error_field, payload=payload):
                response = self.client.post(self.list_url, payload, format="json")

                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn(error_field, response.data)

    def test_create_rejects_duplicate_name_within_company(self):
        response = self.client.post(
            self.list_url,
            {"company": str(self.company.id), "name": self.category.name},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Category.objects.filter(company=self.company, name=self.category.name).count(), 1)

    def test_same_name_is_allowed_for_another_company(self):
        response = self.client.post(
            self.list_url,
            {"company": str(self.other_company.id), "name": self.category.name},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            Category.objects.filter(company=self.other_company, name=self.category.name).exists()
        )

    def test_update(self):
        detail_url = reverse("category-detail", args=[self.category.id])
        payload = {
            "company": str(self.company.id),
            "name": "Updated",
            "parent_category": None,
            "id": str(uuid4()),
        }

        response = self.client.put(detail_url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], str(self.category.id))
        self.assertEqual(response.data["name"], payload["name"])
        self.assertIsNone(response.data["parent_category"])

        self.category.refresh_from_db()
        self.assertEqual(self.category.name, payload["name"])
        self.assertIsNone(self.category.parent_category)

    def test_update_rejects_duplicate_name_within_company(self):
        detail_url = reverse("category-detail", args=[self.category.id])

        response = self.client.patch(
            detail_url,
            {"name": self.parent_category.name},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.category.refresh_from_db()
        self.assertEqual(self.category.name, "Current")

    def test_destroy(self):
        detail_url = reverse("category-detail", args=[self.category.id])
        child = Category.objects.create(
            company=self.company,
            name="Child",
            parent_category=self.category,
        )

        response = self.client.delete(detail_url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Category.objects.filter(id=self.category.id).exists())
        child.refresh_from_db()
        self.assertIsNone(child.parent_category)
        self.assertEqual(self.client.get(detail_url).status_code, status.HTTP_404_NOT_FOUND)
