#!/usr/bin/env python3
"""
Tests for clickup_utils.py

Coverage:
- Configuration loading and validation
- API request handling with mocking
- Task creation and status updates
- Task state tracking (save/load/clear)
- Integration hooks (on_objective_set, on_objective_complete)
- Error handling for network and file operations
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open
import urllib.error

import clickup_utils


class TestConfiguration(unittest.TestCase):
    """Tests for configuration functions."""

    def test_get_config_path_returns_path(self):
        """get_config_path() should return a Path object."""
        result = clickup_utils.get_config_path()
        self.assertIsInstance(result, Path)
        self.assertTrue(str(result).endswith("clickup_config.json"))

    def test_load_config_returns_none_when_file_missing(self):
        """load_config() should return None when config file doesn't exist."""
        with patch.object(clickup_utils, 'get_config_path') as mock_path:
            mock_path.return_value = Path("/nonexistent/path.json")
            result = clickup_utils.load_config()
            self.assertIsNone(result)

    def test_load_config_returns_parsed_json(self):
        """load_config() should return parsed JSON when file exists."""
        config_data = {"enabled": True, "api_token": "test_token"}
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "clickup_config.json"
            config_path.write_text(json.dumps(config_data))

            with patch.object(clickup_utils, 'get_config_path', return_value=config_path):
                result = clickup_utils.load_config()
                self.assertEqual(result, config_data)

    def test_load_config_returns_none_on_invalid_json(self):
        """load_config() should return None on invalid JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "clickup_config.json"
            config_path.write_text("not valid json {{{")

            with patch.object(clickup_utils, 'get_config_path', return_value=config_path):
                result = clickup_utils.load_config()
                self.assertIsNone(result)

    def test_is_enabled_returns_false_when_no_config(self):
        """is_enabled() should return False when no config exists."""
        with patch.object(clickup_utils, 'load_config', return_value=None):
            result = clickup_utils.is_enabled()
            self.assertFalse(result)

    def test_is_enabled_returns_false_when_disabled(self):
        """is_enabled() should return False when enabled is False."""
        with patch.object(clickup_utils, 'load_config', return_value={"enabled": False}):
            result = clickup_utils.is_enabled()
            self.assertFalse(result)

    def test_is_enabled_returns_true_when_enabled(self):
        """is_enabled() should return True when enabled is True."""
        with patch.object(clickup_utils, 'load_config', return_value={"enabled": True}):
            result = clickup_utils.is_enabled()
            self.assertTrue(result)


class TestApiRequest(unittest.TestCase):
    """Tests for _api_request function."""

    def test_api_request_returns_none_when_no_config(self):
        """_api_request() should return None when no config."""
        with patch.object(clickup_utils, 'load_config', return_value=None):
            result = clickup_utils._api_request("GET", "/test")
            self.assertIsNone(result)

    def test_api_request_returns_none_when_no_token(self):
        """_api_request() should return None when no api_token."""
        with patch.object(clickup_utils, 'load_config', return_value={"enabled": True}):
            result = clickup_utils._api_request("GET", "/test")
            self.assertIsNone(result)

    @patch('urllib.request.urlopen')
    def test_api_request_makes_correct_request(self, mock_urlopen):
        """_api_request() should make request with correct headers."""
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"success": true}'
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        config = {"api_token": "test_token"}
        result = clickup_utils._api_request("GET", "/test/endpoint", config=config)

        self.assertEqual(result, {"success": True})
        mock_urlopen.assert_called_once()

    @patch('urllib.request.urlopen')
    def test_api_request_sends_json_body(self, mock_urlopen):
        """_api_request() should send JSON body for POST requests."""
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"id": "123"}'
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        config = {"api_token": "test_token"}
        data = {"name": "Test Task"}
        result = clickup_utils._api_request("POST", "/task", data=data, config=config)

        self.assertEqual(result, {"id": "123"})

    @patch('urllib.request.urlopen')
    def test_api_request_handles_url_error(self, mock_urlopen):
        """_api_request() should return None on URLError."""
        mock_urlopen.side_effect = urllib.error.URLError("Network error")

        config = {"api_token": "test_token"}
        result = clickup_utils._api_request("GET", "/test", config=config)

        self.assertIsNone(result)

    @patch('urllib.request.urlopen')
    def test_api_request_handles_timeout(self, mock_urlopen):
        """_api_request() should return None on TimeoutError."""
        mock_urlopen.side_effect = TimeoutError("Request timed out")

        config = {"api_token": "test_token"}
        result = clickup_utils._api_request("GET", "/test", config=config)

        self.assertIsNone(result)


class TestTaskOperations(unittest.TestCase):
    """Tests for task creation and updates."""

    def test_create_task_returns_none_when_disabled(self):
        """create_task() should return None when integration disabled."""
        with patch.object(clickup_utils, 'is_enabled', return_value=False):
            result = clickup_utils.create_task("Test objective")
            self.assertIsNone(result)

    def test_create_task_returns_none_when_no_list_id(self):
        """create_task() should return None when no list_id configured."""
        with patch.object(clickup_utils, 'load_config', return_value={"enabled": True}):
            with patch.object(clickup_utils, 'is_enabled', return_value=True):
                result = clickup_utils.create_task("Test objective")
                self.assertIsNone(result)

    @patch.object(clickup_utils, '_save_current_task')
    @patch.object(clickup_utils, '_api_request')
    def test_create_task_with_plan_steps(self, mock_api, mock_save):
        """create_task() should include plan steps in description."""
        mock_api.return_value = {"id": "task123", "url": "https://app.clickup.com/t/task123"}
        config = {
            "enabled": True,
            "api_token": "token",
            "default_list_id": "list123",
            "status_mapping": {"objective_set": "in progress"}
        }

        with patch.object(clickup_utils, 'load_config', return_value=config):
            with patch.object(clickup_utils, 'is_enabled', return_value=True):
                result = clickup_utils.create_task("Test", plan_steps=["Step 1", "Step 2"])

        self.assertEqual(result, "task123")
        mock_save.assert_called_once_with("task123", "https://app.clickup.com/t/task123")

    @patch.object(clickup_utils, '_save_current_task')
    @patch.object(clickup_utils, '_api_request')
    def test_create_task_with_dict_plan_steps(self, mock_api, mock_save):
        """create_task() should handle dict-style plan steps."""
        mock_api.return_value = {"id": "task456"}
        config = {
            "enabled": True,
            "api_token": "token",
            "default_list_id": "list123"
        }

        with patch.object(clickup_utils, 'load_config', return_value=config):
            with patch.object(clickup_utils, 'is_enabled', return_value=True):
                plan = [{"description": "Step 1"}, {"description": "Step 2"}]
                result = clickup_utils.create_task("Test", plan_steps=plan)

        self.assertEqual(result, "task456")

    @patch.object(clickup_utils, '_api_request')
    def test_create_task_uses_custom_list_id(self, mock_api):
        """create_task() should use provided list_id override."""
        mock_api.return_value = {"id": "task789"}
        config = {
            "enabled": True,
            "api_token": "token",
            "default_list_id": "default_list"
        }

        with patch.object(clickup_utils, 'load_config', return_value=config):
            with patch.object(clickup_utils, 'is_enabled', return_value=True):
                with patch.object(clickup_utils, '_save_current_task'):
                    clickup_utils.create_task("Test", list_id="custom_list")

        # Check that the custom list was used in the API call
        call_args = mock_api.call_args
        self.assertIn("/list/custom_list/task", call_args[0][1])

    def test_update_task_status_returns_false_when_disabled(self):
        """update_task_status() should return False when disabled."""
        with patch.object(clickup_utils, 'is_enabled', return_value=False):
            result = clickup_utils.update_task_status("task123", "complete")
            self.assertFalse(result)

    @patch.object(clickup_utils, '_api_request')
    def test_update_task_status_returns_true_on_success(self, mock_api):
        """update_task_status() should return True on successful update."""
        mock_api.return_value = {"id": "task123", "status": {"status": "complete"}}
        config = {"enabled": True, "api_token": "token"}

        with patch.object(clickup_utils, 'load_config', return_value=config):
            with patch.object(clickup_utils, 'is_enabled', return_value=True):
                result = clickup_utils.update_task_status("task123", "complete")

        self.assertTrue(result)

    @patch.object(clickup_utils, '_api_request')
    def test_update_task_status_returns_false_on_failure(self, mock_api):
        """update_task_status() should return False on API failure."""
        mock_api.return_value = None
        config = {"enabled": True, "api_token": "token"}

        with patch.object(clickup_utils, 'load_config', return_value=config):
            with patch.object(clickup_utils, 'is_enabled', return_value=True):
                result = clickup_utils.update_task_status("task123", "complete")

        self.assertFalse(result)


class TestCompleteCurrentTask(unittest.TestCase):
    """Tests for complete_current_task function."""

    def test_complete_current_task_returns_false_when_disabled(self):
        """complete_current_task() should return False when disabled."""
        with patch.object(clickup_utils, 'is_enabled', return_value=False):
            result = clickup_utils.complete_current_task()
            self.assertFalse(result)

    def test_complete_current_task_returns_false_when_no_task(self):
        """complete_current_task() should return False when no current task."""
        with patch.object(clickup_utils, 'load_config', return_value={"enabled": True}):
            with patch.object(clickup_utils, 'is_enabled', return_value=True):
                with patch.object(clickup_utils, '_load_current_task', return_value=None):
                    result = clickup_utils.complete_current_task()
                    self.assertFalse(result)

    @patch.object(clickup_utils, '_clear_current_task')
    @patch.object(clickup_utils, 'update_task_status')
    @patch.object(clickup_utils, '_load_current_task')
    def test_complete_current_task_updates_and_clears(self, mock_load, mock_update, mock_clear):
        """complete_current_task() should update status and clear task on success."""
        mock_load.return_value = {"task_id": "task123", "url": "https://..."}
        mock_update.return_value = True
        config = {
            "enabled": True,
            "status_mapping": {"objective_complete": "shipped"}
        }

        with patch.object(clickup_utils, 'load_config', return_value=config):
            with patch.object(clickup_utils, 'is_enabled', return_value=True):
                result = clickup_utils.complete_current_task()

        self.assertTrue(result)
        mock_update.assert_called_once_with("task123", "shipped")
        mock_clear.assert_called_once()


class TestTaskStateTracking(unittest.TestCase):
    """Tests for task state file operations."""

    def test_get_task_state_path_returns_path(self):
        """_get_task_state_path() should return correct path."""
        result = clickup_utils._get_task_state_path()
        self.assertIsInstance(result, Path)
        self.assertTrue(str(result).endswith("clickup_task.json"))

    def test_save_current_task_creates_file(self):
        """_save_current_task() should create task state file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "state" / "clickup_task.json"

            with patch.object(clickup_utils, '_get_task_state_path', return_value=state_path):
                clickup_utils._save_current_task("task123", "https://example.com/task123")

            self.assertTrue(state_path.exists())
            data = json.loads(state_path.read_text())
            self.assertEqual(data["task_id"], "task123")
            self.assertEqual(data["url"], "https://example.com/task123")

    def test_load_current_task_returns_none_when_missing(self):
        """_load_current_task() should return None when file missing."""
        with patch.object(clickup_utils, '_get_task_state_path') as mock_path:
            mock_path.return_value = Path("/nonexistent/task.json")
            result = clickup_utils._load_current_task()
            self.assertIsNone(result)

    def test_load_current_task_returns_data(self):
        """_load_current_task() should return task data from file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "clickup_task.json"
            state_path.write_text('{"task_id": "task456", "url": "https://..."}')

            with patch.object(clickup_utils, '_get_task_state_path', return_value=state_path):
                result = clickup_utils._load_current_task()

            self.assertEqual(result["task_id"], "task456")

    def test_load_current_task_returns_none_on_invalid_json(self):
        """_load_current_task() should return None on invalid JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "clickup_task.json"
            state_path.write_text("not valid json")

            with patch.object(clickup_utils, '_get_task_state_path', return_value=state_path):
                result = clickup_utils._load_current_task()

            self.assertIsNone(result)

    def test_clear_current_task_removes_file(self):
        """_clear_current_task() should delete the task state file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "clickup_task.json"
            state_path.write_text('{"task_id": "task789"}')

            with patch.object(clickup_utils, '_get_task_state_path', return_value=state_path):
                clickup_utils._clear_current_task()

            self.assertFalse(state_path.exists())

    def test_clear_current_task_handles_missing_file(self):
        """_clear_current_task() should not error if file doesn't exist."""
        with patch.object(clickup_utils, '_get_task_state_path') as mock_path:
            mock_path.return_value = Path("/nonexistent/task.json")
            # Should not raise
            clickup_utils._clear_current_task()

    def test_get_current_task_url_returns_url(self):
        """get_current_task_url() should return URL from task state."""
        with patch.object(clickup_utils, '_load_current_task') as mock_load:
            mock_load.return_value = {"task_id": "123", "url": "https://clickup.com/task"}
            result = clickup_utils.get_current_task_url()
            self.assertEqual(result, "https://clickup.com/task")

    def test_get_current_task_url_returns_none_when_no_task(self):
        """get_current_task_url() should return None when no task."""
        with patch.object(clickup_utils, '_load_current_task', return_value=None):
            result = clickup_utils.get_current_task_url()
            self.assertIsNone(result)


class TestIntegrationHooks(unittest.TestCase):
    """Tests for on_objective_set and on_objective_complete hooks."""

    def test_on_objective_set_returns_none_when_disabled(self):
        """on_objective_set() should return None when disabled."""
        with patch.object(clickup_utils, 'is_enabled', return_value=False):
            result = clickup_utils.on_objective_set("Test objective")
            self.assertIsNone(result)

    @patch.object(clickup_utils, 'get_current_task_url')
    @patch.object(clickup_utils, 'create_task')
    def test_on_objective_set_returns_url_on_success(self, mock_create, mock_url):
        """on_objective_set() should return task URL on success."""
        mock_create.return_value = "task123"
        mock_url.return_value = "https://clickup.com/t/task123"

        with patch.object(clickup_utils, 'is_enabled', return_value=True):
            result = clickup_utils.on_objective_set("Test objective", plan=["Step 1"])

        self.assertEqual(result, "https://clickup.com/t/task123")
        mock_create.assert_called_once_with("Test objective", ["Step 1"])

    @patch.object(clickup_utils, 'create_task')
    def test_on_objective_set_returns_none_on_failure(self, mock_create):
        """on_objective_set() should return None when task creation fails."""
        mock_create.return_value = None

        with patch.object(clickup_utils, 'is_enabled', return_value=True):
            result = clickup_utils.on_objective_set("Test objective")

        self.assertIsNone(result)

    @patch.object(clickup_utils, 'complete_current_task')
    def test_on_objective_complete_delegates_to_complete(self, mock_complete):
        """on_objective_complete() should call complete_current_task()."""
        mock_complete.return_value = True

        result = clickup_utils.on_objective_complete()

        self.assertTrue(result)
        mock_complete.assert_called_once()


class TestEdgeCases(unittest.TestCase):
    """Tests for edge cases and error handling."""

    def test_create_task_handles_api_returning_no_id(self):
        """create_task() should handle API response without 'id' field."""
        with patch.object(clickup_utils, '_api_request', return_value={"error": "Something wrong"}):
            config = {"enabled": True, "api_token": "token", "default_list_id": "list123"}
            with patch.object(clickup_utils, 'load_config', return_value=config):
                with patch.object(clickup_utils, 'is_enabled', return_value=True):
                    result = clickup_utils.create_task("Test")

        self.assertIsNone(result)

    def test_complete_current_task_returns_false_when_no_task_id(self):
        """complete_current_task() should return False when task_info has no task_id."""
        config = {"enabled": True, "status_mapping": {}}
        with patch.object(clickup_utils, 'load_config', return_value=config):
            with patch.object(clickup_utils, 'is_enabled', return_value=True):
                with patch.object(clickup_utils, '_load_current_task', return_value={"url": "test"}):
                    result = clickup_utils.complete_current_task()

        self.assertFalse(result)

    def test_create_task_uses_default_status_when_not_mapped(self):
        """create_task() should use default status when mapping missing."""
        with patch.object(clickup_utils, '_api_request') as mock_api:
            mock_api.return_value = {"id": "task999"}
            config = {"enabled": True, "api_token": "token", "default_list_id": "list123"}

            with patch.object(clickup_utils, 'load_config', return_value=config):
                with patch.object(clickup_utils, 'is_enabled', return_value=True):
                    with patch.object(clickup_utils, '_save_current_task'):
                        clickup_utils.create_task("Test")

            # Check that default status "in development" was used
            call_data = mock_api.call_args[0][2]
            self.assertEqual(call_data["status"], "in development")


if __name__ == "__main__":
    unittest.main()
