import json
import os
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from .models import Product


class AssistantChatApiTests(TestCase):
	def setUp(self):
		self.client = APIClient()
		Product.objects.create(
			name="ThinkPad X1",
			model="GenX",
			price="5999.00",
			description="轻薄便携，适合办公与出差。",
			stock=5,
			image="product_images/placeholder.png",
			images=[],
		)
		Product.objects.create(
			name="ThinkPad P1",
			model="Workstation",
			price="12999.00",
			description="高性能，适合剪辑与开发。",
			stock=2,
			image="product_images/placeholder.png",
			images=[],
		)

	@patch("store.assistant.requests.post")
	def test_anonymous_chat_returns_structured_json(self, mock_post):
		os.environ["DASHSCOPE_API_KEY"] = "test-key"
		content = json.dumps(
			{
				"answer": "我推荐一款轻薄办公本。",
				"recommendations": [
					{
						"product_id": Product.objects.get(name="ThinkPad X1").id,
						"highlights": ["轻薄", "办公"],
						"tradeoffs": ["不适合重度游戏"],
						"why_fit": "符合预算与便携需求",
					}
				],
			}
		)

		mock_post.return_value.status_code = 200
		mock_post.return_value.json.return_value = {
			"choices": [{"message": {"content": content}}]
		}

		resp = self.client.post(
			"/assistant/chat/",
			data={"message": "预算 6000，轻薄办公推荐", "budget_max": "6000.00"},
			format="json",
		)

		self.assertEqual(resp.status_code, 200)
		self.assertIn("answer", resp.data)
		self.assertIn("recommendations", resp.data)
		self.assertIn("used_filters", resp.data)
		self.assertIsInstance(resp.data["recommendations"], list)
		self.assertGreaterEqual(len(resp.data["recommendations"]), 1)
		first = resp.data["recommendations"][0]
		# Server must fill these fields from DB
		self.assertIn("name", first)
		self.assertIn("model", first)
		self.assertIn("price", first)
		self.assertIn("stock", first)

	@patch("store.assistant.requests.post")
	def test_budget_filter_empty_catalog_returns_ok(self, mock_post):
		resp = self.client.post(
			"/assistant/chat/",
			data={"message": "预算 1 元", "budget_max": "1.00"},
			format="json",
		)
		self.assertEqual(resp.status_code, 200)
		self.assertEqual(resp.data["recommendations"], [])
		# No upstream call should be made when there are no candidates
		mock_post.assert_not_called()
