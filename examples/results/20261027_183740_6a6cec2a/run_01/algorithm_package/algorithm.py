import math


def plan(request):
    members = request["members"]
    workloads = {u["id"]: 0.0 for u in members}
    positions = {u["id"]: u["start_xy_m"] for u in members}
    assignments = []
    for task in request["tasks"]:
        ends = [(task["x_m"], task["start_y_m"]), (task["x_m"], task["end_y_m"])]
        choices = []
        for uav in members:
            uid = uav["id"]
            direction = min(range(2), key=lambda j: math.dist(positions[uid], ends[j]))
            cost = (math.dist(positions[uid], ends[direction]) + task["length_m"]) / uav["speed_mps"]
            choices.append((workloads[uid] + cost, uid, direction))
        finish, uid, direction = min(choices)
        workloads[uid] = finish
        positions[uid] = ends[1 - direction]
        assignments.append({"task_id": task["id"], "uav_id": uid})
    return {"status": "ok", "assignments": assignments, "unassigned": []}
