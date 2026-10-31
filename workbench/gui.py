"""Local parameterized-model desktop prototype; no cloud service required."""

import copy
import os
import queue
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .experiment import PROJECT_ROOT, run_comparison
from .model import check_model, parameters, read_json, write_json


NAMES = {"coverage_task": "任务区域", "uav_fleet": "无人机编组", "task_allocator": "任务分配算法",
         "serpentine_router": "公共航线生成", "coverage_monitor": "覆盖评价"}
FIELDS = {
    "coverage_task": [("width_m", "区域宽度 / m"), ("height_m", "区域高度 / m"), ("lane_spacing_m", "条带间距 / m"),
                      ("origin_lat_deg", "原点纬度 / °"), ("origin_lon_deg", "原点经度 / °")],
    "uav_fleet": [("altitude_m", "固定高度 / m"), ("bank_angle_limit_deg", "最大坡度角 / °")],
    "task_allocator": [("seed", "算法随机种子"), ("planning_budget_s", "规划进程预算 / s")],
    "serpentine_router": [("turn_padding_m", "条带端点外延 / m")],
    "coverage_monitor": [("footprint_radius_m", "理想足迹半径 / m"), ("grid_resolution_m", "评价网格边长 / m"),
                         ("sample_interval_s", "回放采样间隔 / s")],
}


class WorkbenchApp:
    def __init__(self, root, model_path):
        self.root = root
        self.model = read_json(model_path)
        self.model_path = Path(model_path)
        self.current_index = None
        self.form_vars = {}
        self.member_vars = []
        self.algorithm_vars = []
        self.events = queue.Queue()
        self.running = False
        self.latest_result = None
        root.title("多无人机系统建模与验证工作台 · 原型 0.1")
        root.geometry("1260x800")
        root.minsize(1080, 720)
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure(".", font=("Microsoft YaHei UI", 10))
        style.configure("TButton", padding=(12, 7))
        style.configure("TNotebook.Tab", padding=(18, 8))
        style.configure("Treeview", rowheight=29)
        style.configure("Header.TLabel", font=("Microsoft YaHei UI", 20, "bold"), foreground="#203a5c")
        style.configure("Hint.TLabel", foreground="#64748b")
        shell = ttk.Frame(root, padding=20)
        shell.pack(fill="both", expand=True)
        header = ttk.Frame(shell)
        header.pack(fill="x")
        ttk.Label(header, text="多无人机系统建模与验证", style="Header.TLabel").pack(side="left")
        ttk.Label(header, text="本地 AFSIM  ·  固定任务模板  ·  参数化建模", style="Hint.TLabel").pack(side="right")
        toolbar = ttk.Frame(shell, padding=(0, 16, 0, 12))
        toolbar.pack(fill="x")
        self.name_var = tk.StringVar(value=self.model["name"])
        ttk.Label(toolbar, text="工程名称").pack(side="left")
        ttk.Entry(toolbar, textvariable=self.name_var, width=34).pack(side="left", padx=10)
        self.load_button = ttk.Button(toolbar, text="打开工程", command=self.load)
        self.load_button.pack(side="right", padx=4)
        ttk.Button(toolbar, text="另存工程", command=self.save).pack(side="right", padx=4)
        self.status_var = tk.StringVar(value="就绪。选择模块设置参数，检查模型后运行比较。")
        ttk.Label(shell, textvariable=self.status_var, style="Hint.TLabel", padding=(0, 10, 0, 0)).pack(side="bottom", fill="x")
        self.book = ttk.Notebook(shell)
        self.book.pack(fill="both", expand=True)
        self.model_tab, self.run_tab, self.results_tab, self.help_tab = [ttk.Frame(self.book, padding=14) for _ in range(4)]
        for tab, title in zip((self.model_tab, self.run_tab, self.results_tab, self.help_tab), ("工程建模", "检查与执行", "比较结果", "范围与接入")):
            self.book.add(tab, text=title)
        self.build_model_tab()
        self.build_run_tab()
        self.build_results_tab()
        self.build_help_tab()
        self.refresh_model_list()
        root.after(150, self.poll_events)

    def build_model_tab(self):
        split = ttk.Panedwindow(self.model_tab, orient="horizontal")
        split.pack(fill="both", expand=True)
        left = ttk.Frame(split, padding=(0, 0, 15, 0))
        right = ttk.Frame(split, padding=(18, 0, 0, 0))
        split.add(left, weight=3)
        split.add(right, weight=2)
        ttk.Label(left, text="模块与连接", font=("Microsoft YaHei UI", 12, "bold")).pack(anchor="w")
        self.module_list = ttk.Treeview(left, columns=("kind",), show="tree headings", height=6)
        self.module_list.heading("#0", text="模块编号")
        self.module_list.heading("kind", text="模块类型")
        self.module_list.column("#0", width=110, stretch=False)
        self.module_list.column("kind", width=220)
        self.module_list.pack(fill="x", pady=(10, 12))
        self.module_list.bind("<<TreeviewSelect>>", self.select_module)
        self.diagram = tk.Canvas(left, background="#f4f7fb", height=210, highlightthickness=0)
        self.diagram.pack(fill="x")
        self.diagram.bind("<Configure>", lambda event: self.draw_diagram())
        ttk.Label(left, text="执行流程", font=("Microsoft YaHei UI", 11, "bold")).pack(anchor="w", pady=(16, 8))
        ttk.Label(left, text="初始化 → 算法分配 → 公共航线 → AFSIM 执行 → 评价", wraplength=560).pack(anchor="w")
        ttk.Label(left, text="模型包含结构、参数、固定行为模板和需求追踪。\n当前支持预置模块组合，暂未开放自由增删模块与连线。", style="Hint.TLabel", wraplength=550).pack(anchor="w", pady=14)
        self.form_title = ttk.Label(right, text="模块参数", font=("Microsoft YaHei UI", 12, "bold"))
        self.form_title.pack(anchor="w", pady=(0, 12))
        self.form = ttk.Frame(right)
        self.form.pack(fill="both", expand=True)
        self.apply_button = ttk.Button(right, text="应用模块参数", command=self.apply_current)
        self.apply_button.pack(anchor="e", pady=10)

    def build_run_tab(self):
        settings = ttk.LabelFrame(self.run_tab, text="执行与需求", padding=12)
        settings.pack(fill="x")
        self.engine_var = tk.StringVar(value=self.model["engine"]["afsim_home"])
        self.horizon_var = tk.StringVar(value=str(self.model["engine"]["horizon_s"]))
        self.cover_var = tk.StringVar(value=str(next(r["threshold"] for r in self.model["requirements"] if r["metric"] == "coverage_pct")))
        self.deadline_var = tk.StringVar(value=str(next(r["threshold"] for r in self.model["requirements"] if r["metric"] == "coverage_threshold_time_s")))
        ttk.Label(settings, text="AFSIM 目录").grid(row=0, column=0, sticky="w", padx=5)
        ttk.Entry(settings, textvariable=self.engine_var, width=66).grid(row=0, column=1, columnspan=5, sticky="ew", padx=10, pady=6)
        ttk.Button(settings, text="选择目录", command=self.choose_engine).grid(row=0, column=6)
        for i, (label, var) in enumerate((("仿真时限 / s", self.horizon_var), ("覆盖率需求 / %", self.cover_var), ("达到阈值期限 / s", self.deadline_var))):
            ttk.Label(settings, text=label).grid(row=1, column=2*i, sticky="w", padx=5, pady=12)
            ttk.Entry(settings, textvariable=var, width=10).grid(row=1, column=2*i+1, sticky="w", padx=10)
        actions = ttk.Frame(self.run_tab, padding=(0, 16))
        actions.pack(fill="x")
        self.check_button = ttk.Button(actions, text="检查工程模型", command=self.check)
        self.check_button.pack(side="left")
        self.run_button = ttk.Button(actions, text="生成场景并运行 A/B 比较", command=self.run)
        self.run_button.pack(side="left", padx=12)
        self.progressbar = ttk.Progressbar(actions, mode="indeterminate", length=200)
        self.progressbar.pack(side="right")
        self.log = tk.Text(self.run_tab, height=15, wrap="word", font=("Microsoft YaHei UI", 10), relief="flat", padx=14, pady=12)
        self.log.pack(fill="both", expand=True)
        self.log.insert("end", "模型检查和运行过程将在此显示。每次比较保存独立的工程快照、算法输入输出、生成场景、回放及指标。\n")
        self.log.configure(state="disabled")

    def build_results_tab(self):
        ttk.Label(self.results_tab, text="原始差异 = 候选 B − 参照 A；覆盖率使用百分点。未达阈值的时间不计算差值。", wraplength=1000).pack(anchor="w", pady=(0, 12))
        self.result_tree = ttk.Treeview(self.results_tab, columns=("metric", "a", "b", "delta"), show="headings", height=6)
        for key, label, width in (("metric", "指标", 300), ("a", "参照 A", 150), ("b", "候选 B", 150), ("delta", "原始差异", 200)):
            self.result_tree.heading(key, text=label)
            self.result_tree.column(key, width=width)
        self.result_tree.pack(fill="x")
        ttk.Label(self.results_tab, text="需求判定与证据", font=("Microsoft YaHei UI", 12, "bold")).pack(anchor="w", pady=(20, 10))
        self.requirement_tree = ttk.Treeview(self.results_tab, columns=("algorithm", "requirement", "actual", "status"), show="headings", height=6)
        for key, label, width in (("algorithm", "算法", 250), ("requirement", "需求", 300), ("actual", "实际值", 140), ("status", "判定", 140)):
            self.requirement_tree.heading(key, text=label)
            self.requirement_tree.column(key, width=width)
        self.requirement_tree.pack(fill="x")
        self.result_note = tk.StringVar(value="尚无实验结果。一次示例不用于统计显著性或实机能力结论。")
        ttk.Label(self.results_tab, textvariable=self.result_note, wraplength=1080, style="Hint.TLabel").pack(anchor="w", pady=18)
        actions = ttk.Frame(self.results_tab)
        actions.pack(fill="x")
        ttk.Button(actions, text="打开轨迹与结果预览", command=self.open_preview).pack(side="left")
        ttk.Button(actions, text="打开证据目录", command=self.open_evidence).pack(side="left", padx=12)

    def build_help_tab(self):
        text = tk.Text(self.help_tab, wrap="word", font=("Microsoft YaHei UI", 11), relief="flat", padx=16, pady=14)
        text.pack(fill="both", expand=True)
        text.insert("end", "第一版已实现\n\n工程模型与类型化端口检查、需求追踪检查、参数编辑、独立算法进程、公共航线生成、AFSIM 运行、实际回放解析、覆盖差异与需求判定。\n\n算法接入\n\n复制 algorithms/round_robin 作为算法包，修改 manifest.json，提供 plan(request) 函数。输入包括任务条带、成员、约束和种子；输出 assignments 及有原因的 unassigned。任务不得重复或静默遗漏。接入自检会在正式比较中检查输出。算法包使用本机 Python 环境；暂不自动安装依赖，不构成运行不可信代码的安全隔离环境。\n\n当前边界\n\n仅支持离线任务分配、固定区域覆盖模板及本机 AFSIM 2.9。使用平坦区域和理想圆形足迹，不模拟真实探测、通信、碰撞、能耗或在线重规划。载荷全程启用，转场路径也计入覆盖。单个确定性示例没有置信区间或普适性能结论。\n\n后续方向\n\n模块自由组合与行为编辑、更多验证任务、通信及资源契约、变更影响与定向重验证、在线算法桥接。正式报告格式后续确定。\n\n所有结果均保留工程配置、算法版本和原始证据，可从比较结果页打开。")
        text.configure(state="disabled")

    def draw_diagram(self):
        self.diagram.delete("all")
        width = max(self.diagram.winfo_width(), 480)
        positions = {"coverage_task": (0.17, 45), "task_allocator": (0.50, 45), "serpentine_router": (0.83, 45),
                     "uav_fleet": (0.31, 145), "coverage_monitor": (0.72, 145)}
        for connection in self.model["connections"]:
            source, target = connection["from"].split(".")[0], connection["to"].split(".")[0]
            sm = next(m for m in self.model["modules"] if m["id"] == source)
            tm = next(m for m in self.model["modules"] if m["id"] == target)
            x1, y1 = positions[sm["type"]]
            x2, y2 = positions[tm["type"]]
            self.diagram.create_line(x1*width, y1, x2*width, y2, fill="#a7b5c9", width=2, arrow="last")
        for index, module in enumerate(self.model["modules"]):
            x, y = positions[module["type"]]
            x *= width
            selected = index == self.current_index
            tag = f"module_{index}"
            self.diagram.create_rectangle(x-66, y-27, x+66, y+27, fill="#dfeaff" if selected else "white", outline="#3574c4" if selected else "#bcc9d9", width=2, tags=tag)
            self.diagram.create_text(x, y, text=NAMES[module["type"]], fill="#254364", font=("Microsoft YaHei UI", 10), tags=tag)
            self.diagram.tag_bind(tag, "<Button-1>", lambda event, i=index: self.module_list.selection_set(str(i)))

    def refresh_model_list(self):
        self.current_index = None
        self.module_list.delete(*self.module_list.get_children())
        for index, module in enumerate(self.model["modules"]):
            self.module_list.insert("", "end", iid=str(index), text=module["id"], values=(NAMES[module["type"]],))
        self.module_list.selection_set("0")
        self.select_module()

    def select_module(self, event=None):
        selected = self.module_list.selection()
        if not selected:
            return
        index = int(selected[0])
        if index == self.current_index:
            return
        if self.current_index is not None and not self.apply_current(quiet=True):
            self.module_list.selection_set(str(self.current_index))
            return
        self.current_index = index
        module = self.model["modules"][index]
        kind, params = module["type"], module["parameters"]
        self.form_title.configure(text=f"{module['id']} · {NAMES[kind]}")
        for widget in self.form.winfo_children():
            widget.destroy()
        self.form_vars, self.member_vars, self.algorithm_vars = {}, [], []
        for row, (key, label) in enumerate(FIELDS[kind]):
            ttk.Label(self.form, text=label).grid(row=row, column=0, sticky="w", pady=7)
            var = tk.StringVar(value=str(params[key]))
            self.form_vars[key] = var
            ttk.Entry(self.form, textvariable=var, width=21).grid(row=row, column=1, sticky="ew", padx=(14, 0))
        row = len(FIELDS[kind])
        if kind == "task_allocator":
            for i, path in enumerate(params["algorithm_packages"]):
                ttk.Label(self.form, text="参照算法 A" if i == 0 else "候选算法 B").grid(row=row, column=0, sticky="w", pady=(14, 4))
                row += 1
                var = tk.StringVar(value=path)
                self.algorithm_vars.append(var)
                ttk.Entry(self.form, textvariable=var, width=32).grid(row=row, column=0, columnspan=2, sticky="ew")
                row += 1
                ttk.Button(self.form, text="选择算法包目录", command=lambda v=var: self.choose_package(v)).grid(row=row, column=0, columnspan=2, sticky="w", pady=5)
                row += 1
        if kind == "uav_fleet":
            ttk.Label(self.form, text="成员 / 速度(m/s) / 东坐标(m) / 北坐标(m)", style="Hint.TLabel").grid(row=row, column=0, columnspan=2, sticky="w", pady=10)
            row += 1
            for uav in params["uavs"]:
                frame = ttk.Frame(self.form)
                frame.grid(row=row, column=0, columnspan=2, sticky="w", pady=3)
                ttk.Label(frame, text=uav["id"], width=9).pack(side="left")
                variables = [tk.StringVar(value=str(v)) for v in (uav["speed_mps"], *uav["start_xy_m"])]
                self.member_vars.append((uav["id"], variables))
                for var in variables:
                    ttk.Entry(frame, textvariable=var, width=7).pack(side="left", padx=3)
                row += 1
            frame = ttk.Frame(self.form)
            frame.grid(row=row, column=0, columnspan=2, sticky="w", pady=10)
            ttk.Button(frame, text="增加成员", command=lambda: self.change_member(1)).pack(side="left")
            ttk.Button(frame, text="移除末位", command=lambda: self.change_member(-1)).pack(side="left", padx=8)
        self.draw_diagram()

    def apply_current(self, quiet=False):
        try:
            if self.current_index is None:
                return True
            module = self.model["modules"][self.current_index]
            params = copy.deepcopy(module["parameters"])
            for key, var in self.form_vars.items():
                params[key] = int(var.get()) if key == "seed" else float(var.get())
            if self.algorithm_vars:
                params["algorithm_packages"] = [v.get() for v in self.algorithm_vars]
            if self.member_vars:
                params["uavs"] = [{"id": uid, "speed_mps": float(v[0].get()), "start_xy_m": [float(v[1].get()), float(v[2].get())]} for uid, v in self.member_vars]
            module["parameters"] = params
            if not quiet:
                self.status_var.set(f"已应用 {module['id']} 参数；运行前将执行完整检查。")
            return True
        except ValueError:
            messagebox.showerror("参数格式", "数值格式无效，请检查当前模块参数。")
            return False

    def change_member(self, delta):
        if not self.apply_current(quiet=True):
            return
        params = self.model["modules"][self.current_index]["parameters"]
        members = params["uavs"]
        if delta > 0 and len(members) < 10:
            ids = {u["id"] for u in members}
            n = 1
            while f"UAV_{n}" in ids:
                n += 1
            task = parameters(self.model, "coverage_task")
            members.append({"id": f"UAV_{n}", "speed_mps": 15, "start_xy_m": [task["width_m"] / 2, -60]})
        elif delta < 0 and len(members) > 1:
            members.pop()
        index = self.current_index
        self.current_index = None
        self.module_list.selection_set(str(index))
        self.select_module()

    def apply_all(self):
        if not self.apply_current(quiet=True):
            return False
        try:
            self.model["name"] = self.name_var.get()
            self.model["engine"]["afsim_home"] = self.engine_var.get()
            self.model["engine"]["horizon_s"] = float(self.horizon_var.get())
            for req in self.model["requirements"]:
                req["threshold"] = float(self.cover_var.get() if req["metric"] == "coverage_pct" else self.deadline_var.get())
            return True
        except ValueError:
            messagebox.showerror("参数格式", "实验时限与需求阈值需要有效数值。")
            return False

    def append_log(self, message):
        self.log.configure(state="normal")
        self.log.insert("end", message + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def check(self):
        if not self.apply_all():
            return False
        self.book.select(self.run_tab)
        issues = check_model(self.model, PROJECT_ROOT)
        self.append_log("\n工程检查：")
        for issue in issues:
            self.append_log(f"[{issue['level']}] {issue['path']}：{issue['message']}")
        valid = not any(i["level"] == "error" for i in issues)
        self.status_var.set("模型检查通过，可以执行；请注意适用范围。" if valid else "模型检查未通过，请修正错误。")
        return valid

    def run(self):
        if self.running or not self.check():
            return
        self.running = True
        for button in (self.run_button, self.check_button, self.load_button, self.apply_button):
            button.configure(state="disabled")
        self.progressbar.start()
        snapshot = copy.deepcopy(self.model)

        def worker():
            try:
                result = run_comparison(snapshot, progress=lambda text: self.events.put(("log", text)))
                self.events.put(("result", result))
            except Exception as exc:
                self.events.put(("error", str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def poll_events(self):
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "log":
                    self.append_log(payload)
                    self.status_var.set(payload)
                else:
                    self.running = False
                    self.progressbar.stop()
                    for button in (self.run_button, self.check_button, self.load_button, self.apply_button):
                        button.configure(state="normal")
                    if kind == "error":
                        self.append_log("执行失败：" + payload)
                        self.status_var.set("执行失败，详见运行记录。")
                    else:
                        self.show_result(payload)
        except queue.Empty:
            pass
        self.root.after(150, self.poll_events)

    def show_result(self, result):
        self.latest_result = result
        self.result_tree.delete(*self.result_tree.get_children())
        self.requirement_tree.delete(*self.requirement_tree.get_children())
        fmt = lambda v: "不适用" if v is None else f"{v:.3f}"
        for row in result["comparison"]["differences"]:
            self.result_tree.insert("", "end", values=(row["label"], fmt(row["baseline"]), fmt(row["candidate"]), f"{fmt(row['delta'])} {row['unit']}"))
        for run in result["comparison"]["runs"]:
            name = run.get("algorithm", {}).get("name", run["package"])
            if run["status"] != "completed":
                self.requirement_tree.insert("", "end", values=(name, run.get("error", run["status"]), "—", "执行未完成"))
            for req in run.get("requirements", []):
                self.requirement_tree.insert("", "end", values=(name, f"{req['id']} · {req['name']}", fmt(req["actual"]), "通过" if req["status"] == "pass" else "未通过"))
        self.result_note.set("单个确定性任务实例。结果与全部证据已保存：\n" + result["directory"])
        self.status_var.set("比较完成。指标改善和需求是否满足请分别查看。")
        self.book.select(self.results_tab)

    def choose_package(self, var):
        path = filedialog.askdirectory(title="选择包含 manifest.json 的算法包目录")
        if path:
            var.set(path)

    def choose_engine(self):
        path = filedialog.askdirectory(title="选择 AFSIM 安装根目录")
        if path:
            self.engine_var.set(path)

    def load(self):
        path = filedialog.askopenfilename(title="打开工程", filetypes=[("工程模型", "*.json")])
        if not path:
            return
        try:
            model = read_json(path)
            errors = [i for i in check_model(model, PROJECT_ROOT, check_engine=False) if i["level"] == "error"]
            if errors:
                raise ValueError("\n".join(f"{i['path']}：{i['message']}" for i in errors))
            self.model = model
            self.model_path = Path(path)
            self.name_var.set(model["name"])
            self.engine_var.set(model["engine"]["afsim_home"])
            self.horizon_var.set(str(model["engine"]["horizon_s"]))
            self.cover_var.set(str(next(r["threshold"] for r in model["requirements"] if r["metric"] == "coverage_pct")))
            time_req = next((r for r in model["requirements"] if r["metric"] == "coverage_threshold_time_s"), None)
            self.deadline_var.set(str(time_req["threshold"] if time_req else model["engine"]["horizon_s"]))
            self.refresh_model_list()
            self.status_var.set(f"已打开工程：{path}")
        except Exception as exc:
            messagebox.showerror("打开失败", str(exc))

    def save(self):
        if not self.apply_all():
            return
        path = filedialog.asksaveasfilename(title="另存工程", defaultextension=".json", filetypes=[("工程模型", "*.json")], initialfile="my_project.json")
        if path:
            write_json(path, self.model)
            self.status_var.set(f"已保存工程：{path}")

    def open_preview(self):
        if self.latest_result:
            webbrowser.open(Path(self.latest_result["preview"]).as_uri())

    def open_evidence(self):
        if self.latest_result:
            os.startfile(self.latest_result["directory"])


def launch(model_path):
    root = tk.Tk()
    WorkbenchApp(root, model_path)
    root.mainloop()
