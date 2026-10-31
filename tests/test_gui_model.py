"""Widget/model integration checks with an undisplayed test window."""

import tkinter as tk
import unittest

from workbench.experiment import PROJECT_ROOT
from workbench.gui import WorkbenchApp
from workbench.model import parameters


class GuiModelIntegration(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.app = WorkbenchApp(self.root, PROJECT_ROOT / "examples/coverage_project.json")

    def tearDown(self):
        self.root.destroy()

    def test_parameter_form_writes_same_model(self):
        self.app.form_vars["width_m"].set("720")
        self.assertTrue(self.app.apply_all())
        self.assertEqual(parameters(self.app.model, "coverage_task")["width_m"], 720)

    def test_add_and_remove_member_updates_model(self):
        self.app.module_list.selection_set("1")
        self.app.select_module()
        self.app.change_member(1)
        self.assertEqual(len(parameters(self.app.model, "uav_fleet")["uavs"]), 3)
        self.app.change_member(-1)
        self.assertEqual(len(parameters(self.app.model, "uav_fleet")["uavs"]), 2)


if __name__ == "__main__":
    unittest.main()
