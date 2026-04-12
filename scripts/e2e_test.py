"""End-to-end test: WebSocket → Orchestrator → Real LLM → Response.

Connects to the running backend via WebSocket, sends a real EUV support
question, and verifies the full pipeline works with real LLM responses.
"""

import asyncio
import json
import sys

import websockets


async def run_e2e():
    url = "ws://localhost:8000/ws"
    print(f"Connecting to {url}...")

    async with websockets.connect(url) as ws:
        print("Connected!")

        # Send a real EUV support question
        message = {
            "type": "user_message",
            "payload": {
                "text": "We are experiencing E4012 stage synchronization error on PROVE tool after PM. What are the common causes and recommended troubleshooting steps?",
                "silo": {
                    "account": "SEC",
                    "tool": "PROVE",
                    "component": "Stage",
                },
            },
        }

        print(f"\nSending: {message['payload']['text'][:80]}...")
        await ws.send(json.dumps(message))

        # Collect all responses until completion
        responses = []
        timeout = 120  # 2 minutes max
        agents_heard = set()

        try:
            async with asyncio.timeout(timeout):
                while True:
                    raw = await ws.recv()
                    data = json.loads(raw)
                    responses.append(data)

                    msg_type = data.get("type")
                    payload = data.get("payload", {})

                    if msg_type == "status_update":
                        agent = payload.get("agent", "")
                        status = payload.get("status", "")
                        if agent:
                            print(f"  [{agent}] status: {status}")
                        elif status == "processing":
                            print(f"  Case ID: {payload.get('case_id')}")
                        elif status == "complete":
                            print(f"\n  COMPLETE — rounds: {payload.get('round_count')}, "
                                  f"reason: {payload.get('terminated_reason')}")
                            break

                    elif msg_type == "agent_message":
                        agent = payload.get("agent", "?")
                        ctype = payload.get("contributionType", "")
                        content = payload.get("content", "")
                        agents_heard.add(agent)
                        preview = content[:150].replace("\n", " ")
                        print(f"  [{agent}] ({ctype}) {preview}...")

                    elif msg_type == "error":
                        print(f"  ERROR: {payload.get('message')}")
                        break

        except TimeoutError:
            print(f"\nTimed out after {timeout}s")

        # Summary
        print("\n" + "=" * 60)
        print("E2E TEST SUMMARY")
        print("=" * 60)

        agent_msgs = [r for r in responses if r.get("type") == "agent_message"]
        status_msgs = [r for r in responses if r.get("type") == "status_update"]
        error_msgs = [r for r in responses if r.get("type") == "error"]

        print(f"Total messages received: {len(responses)}")
        print(f"Agent responses: {len(agent_msgs)}")
        print(f"Status updates: {len(status_msgs)}")
        print(f"Errors: {len(error_msgs)}")
        print(f"Agents heard from: {sorted(agents_heard)}")

        # Validation
        ok = True
        if error_msgs:
            print("\nFAIL: Got error messages")
            for e in error_msgs:
                print(f"  - {e['payload'].get('message')}")
            ok = False

        if len(agent_msgs) == 0:
            print("\nFAIL: No agent messages received")
            ok = False

        # Check we got completion
        completed = any(
            r.get("type") == "status_update" and r.get("payload", {}).get("status") == "complete"
            for r in responses
        )
        if not completed:
            print("\nFAIL: Did not receive completion status")
            ok = False

        if ok:
            print("\nPASS: E2E test succeeded!")
            print("\n--- Agent Responses ---")
            for msg in agent_msgs:
                p = msg["payload"]
                print(f"\n[{p['agent']}] ({p.get('contributionType', '')})")
                print(p.get("content", "")[:500])
        else:
            print("\nFAIL: E2E test failed")
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run_e2e())
