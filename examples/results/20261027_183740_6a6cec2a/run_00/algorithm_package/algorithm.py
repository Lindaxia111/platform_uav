def plan(request):
    members = request["members"]
    return {"status": "ok", "assignments": [
        {"task_id": task["id"], "uav_id": members[i % len(members)]["id"]}
        for i, task in enumerate(request["tasks"])
    ], "unassigned": []}
