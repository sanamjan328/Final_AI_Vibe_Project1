"""Tests for /api/health."""

from __future__ import annotations


def test_health_simulator_mode(client, monkeypatch):
    monkeypatch.delenv("MASSIVE_API_KEY", raising=False)
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "mode": "simulator"}


def test_health_massive_mode(client, monkeypatch):
    monkeypatch.setenv("MASSIVE_API_KEY", "fake-key")
    r = client.get("/api/health")
    assert r.json() == {"status": "ok", "mode": "massive"}
