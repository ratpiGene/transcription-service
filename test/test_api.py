def seed_uploaded_job(app_module, job_id: str, input_type: str = "video"):
    suffix = ".mp4" if input_type == "video" else ".wav"
    app_module.set_status(
        job_id,
        {
            "job_id": job_id,
            "status": "uploaded",
            "created_at": 1234567890.0,
            "input": {
                "bucket": "transcript-uploads",
                "key": f"{job_id}/input{suffix}",
                "type": input_type,
            },
            "available_outputs": app_module.available_outputs_for(
                app_module.InputType(input_type)
            ),
        },
    )


def test_get_job_not_found(client):
    resp = client.get("/jobs/job_unknown")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "job_not_found"


def test_list_jobs_by_client_empty(client):
    resp = client.get("/jobs", params={"client_id": "client-empty"})
    assert resp.status_code == 200
    assert resp.json() == {
        "client_id": "client-empty",
        "count": 0,
        "jobs": [],
    }


def test_create_job_requires_job_id(client):
    resp = client.post("/jobs", json={"requested_outputs": ["transcript_text"]})
    assert resp.status_code == 422
    assert resp.json()["detail"] == "job_id required"


def test_create_job_requires_outputs(client):
    resp = client.post("/jobs", json={"job_id": "job_123"})
    assert resp.status_code == 422
    assert resp.json()["detail"] == "requested_outputs must be a list"


def test_create_job_returns_404_if_job_unknown(client):
    resp = client.post(
        "/jobs",
        json={
            "job_id": "job_missing",
            "requested_outputs": ["transcript_text"],
        },
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "job_not_found"


def test_create_job_rejects_unknown_output_type(client, app_module):
    seed_uploaded_job(app_module, "job_video_1", input_type="video")

    resp = client.post(
        "/jobs",
        json={
            "job_id": "job_video_1",
            "requested_outputs": ["not_a_real_output"],
        },
    )

    assert resp.status_code == 422
    assert resp.json()["detail"] == "unknown_output_type"


def test_create_job_rejects_video_output_for_audio_input(client, app_module):
    seed_uploaded_job(app_module, "job_audio_1", input_type="audio")

    resp = client.post(
        "/jobs",
        json={
            "job_id": "job_audio_1",
            "requested_outputs": ["video_embedded"],
        },
    )

    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["invalid_outputs"] == ["video_embedded"]
    assert "transcript_text" in detail["allowed"]
    assert "subtitles_srt" in detail["allowed"]


def test_create_job_success_sets_status_and_indexes_client(client, app_module):
    seed_uploaded_job(app_module, "job_video_2", input_type="video")

    resp = client.post(
        "/jobs",
        json={
            "job_id": "job_video_2",
            "requested_outputs": ["transcript_text", "subtitles_srt"],
            "client_id": "client-123",
        },
    )

    assert resp.status_code == 200
    assert resp.json() == {
        "job_id": "job_video_2",
        "status": "queued",
    }

    status = app_module.get_status("job_video_2")
    assert status["status"] == "queued"
    assert status["requested_outputs"] == ["transcript_text", "subtitles_srt"]
    assert status["client_id"] == "client-123"

    assert "job_video_2" in app_module.get_client_job_ids("client-123")
    assert "job_video_2" in app_module._enqueued_jobs


def test_list_jobs_by_client_returns_jobs(client, app_module):
    seed_uploaded_job(app_module, "job_a", input_type="video")
    seed_uploaded_job(app_module, "job_b", input_type="audio")

    app_module.add_job_to_client("client-xyz", "job_a")
    app_module.add_job_to_client("client-xyz", "job_b")

    resp = client.get("/jobs", params={"client_id": "client-xyz"})

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["client_id"] == "client-xyz"
    assert payload["count"] == 2

    returned_ids = [job["job_id"] for job in payload["jobs"]]
    assert returned_ids == ["job_b", "job_a"]