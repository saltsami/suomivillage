#!/usr/bin/env -S bash -c '"$(dirname "$0")/../venv/bin/python3" "$0" "$@"'
"""
Koivulahti Village Monitor - Live activity feed for the simulation.

Usage:
    ./tools/village_monitor.py               # Show recent activity
    ./tools/village_monitor.py --live        # Live updating feed
    ./tools/village_monitor.py --npc sanni   # Filter by NPC
    ./tools/village_monitor.py --type SMALL_TALK  # Filter by event type

Requires: pip install psycopg2-binary rich
Or use venv: source venv/bin/activate
"""

import argparse
import os
import sys
import time
import socket
import subprocess
from datetime import datetime, timezone
from typing import Optional
from urllib.request import urlopen
from urllib.error import URLError

try:
    import psycopg2
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.live import Live
    from rich.text import Text
    from rich.layout import Layout
except ImportError:
    print("Missing packages. Run:")
    print("  source venv/bin/activate && pip install psycopg2-binary rich")
    sys.exit(1)

console = Console()

# Event type colors
EVENT_COLORS = {
    "SMALL_TALK": "cyan",
    "LOCATION_VISIT": "green",
    "CUSTOMER_INTERACTION": "yellow",
    "INSULT": "red",
    "COMPLIMENT": "magenta",
    "HELP_GIVEN": "bright_green",
    "HELP_REFUSED": "red",
    "APOLOGY": "blue",
    "TRADE_COMPLETE": "yellow",
    "RUMOR_SPREAD": "bright_magenta",
}

CHANNEL_COLORS = {
    "FEED": "bright_blue",
    "CHAT": "bright_cyan",
    "NEWS": "bright_yellow",
}


def get_db_connection():
    """Get database connection from environment or defaults."""
    db_url = os.environ.get(
        "DATABASE_URL",
        "postgresql://koivulahti:koivulahti@localhost:5432/koivulahti"
    )
    return psycopg2.connect(db_url)


def check_service(url: str, timeout: float = 1.0) -> tuple[bool, str]:
    """Check if a HTTP service is responding."""
    try:
        resp = urlopen(url, timeout=timeout)
        return True, "ok"
    except URLError as e:
        return False, "down"
    except Exception:
        return False, "err"


def check_docker_container(name: str) -> tuple[bool, str]:
    """Check if a docker container is running."""
    try:
        result = subprocess.run(
            ["docker", "ps", "--filter", f"name={name}", "--format", "{{.Status}}"],
            capture_output=True, text=True, timeout=2
        )
        status = result.stdout.strip()
        if not status:
            return False, "stopped"
        if "unhealthy" in status.lower():
            return True, "unhealthy"
        if "healthy" in status.lower() or "Up" in status:
            return True, "ok"
        return True, status[:10]
    except Exception:
        return False, "err"


def get_services_status() -> dict:
    """Check all services and return their status."""
    services = {}

    # HTTP endpoints
    endpoints = {
        "api": "http://localhost:8082/health",
        "gateway": "http://localhost:8081/health",
        "llm": "http://localhost:8080/health",
    }
    for name, url in endpoints.items():
        ok, status = check_service(url)
        services[name] = {"ok": ok, "status": status}

    # Docker containers (for non-HTTP services)
    containers = {
        "engine": "koivulahti-engine",
        "decision": "koivulahti-decision-service",
        "workers": "koivulahti-workers",
        "redis": "koivulahti-redis",
        "db": "koivulahti-postgres",
    }
    for name, container in containers.items():
        ok, status = check_docker_container(container)
        services[name] = {"ok": ok, "status": status}

    return services


def fetch_recent_events(
    conn,
    limit: int = 20,
    npc_filter: Optional[str] = None,
    type_filter: Optional[str] = None,
) -> list:
    """Fetch recent events from database."""
    query = """
        SELECT id, type, actors, targets, place_id, sim_ts, ts, payload
        FROM events
        WHERE 1=1
    """
    params = []

    if npc_filter:
        query += " AND (actors::text LIKE %s OR targets::text LIKE %s)"
        params.extend([f"%{npc_filter}%", f"%{npc_filter}%"])

    if type_filter:
        query += " AND type = %s"
        params.append(type_filter)

    query += " ORDER BY ts DESC LIMIT %s"
    params.append(limit)

    with conn.cursor() as cur:
        cur.execute(query, params)
        return cur.fetchall()


def fetch_recent_decisions(
    conn,
    limit: int = 10,
    npc_filter: Optional[str] = None,
    action_filter: Optional[str] = None,
) -> list:
    """Fetch recent decisions from database."""
    query = """
        SELECT job_id, npc_id, stimulus_type, action, intent, emotion,
               llm_output->>'draft' as draft,
               llm_output->>'reasoning' as reasoning,
               latency_ms, error, processed_at
        FROM decisions
        WHERE 1=1
    """
    params = []

    if npc_filter:
        query += " AND npc_id = %s"
        params.append(npc_filter)

    if action_filter:
        query += " AND action = %s"
        params.append(action_filter)

    query += " ORDER BY processed_at DESC LIMIT %s"
    params.append(limit)

    with conn.cursor() as cur:
        cur.execute(query, params)
        return cur.fetchall()


def fetch_recent_posts(
    conn,
    limit: int = 10,
    npc_filter: Optional[str] = None,
    channel_filter: Optional[str] = None,
) -> list:
    """Fetch recent posts from database."""
    query = """
        SELECT id, author_id, channel, text, tone, created_at, source_event_id
        FROM posts
        WHERE 1=1
    """
    params = []

    if npc_filter:
        query += " AND author_id = %s"
        params.append(npc_filter)

    if channel_filter:
        query += " AND channel = %s"
        params.append(channel_filter)

    query += " ORDER BY created_at DESC LIMIT %s"
    params.append(limit)

    with conn.cursor() as cur:
        cur.execute(query, params)
        return cur.fetchall()


def fetch_stats(conn) -> dict:
    """Fetch simulation statistics."""
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM events")
        event_count = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM posts")
        post_count = cur.fetchone()[0]

        cur.execute("SELECT MAX(sim_ts) FROM events")
        latest_sim_ts = cur.fetchone()[0]

        cur.execute("SELECT MAX(ts) FROM events")
        latest_real_ts = cur.fetchone()[0]

        # Decision stats
        cur.execute("SELECT COUNT(*) FROM decisions")
        decision_count = cur.fetchone()[0]

        cur.execute("""
            SELECT
                COUNT(*) FILTER (WHERE action != 'IGNORE') as active,
                AVG(latency_ms) FILTER (WHERE latency_ms > 0) as avg_latency,
                COUNT(*) FILTER (WHERE error IS NOT NULL) as errors
            FROM decisions
            WHERE processed_at > NOW() - INTERVAL '5 minutes'
        """)
        row = cur.fetchone()
        recent_active = row[0] or 0
        avg_latency = row[1] or 0
        recent_errors = row[2] or 0

        return {
            "events": event_count,
            "posts": post_count,
            "decisions": decision_count,
            "recent_active": recent_active,
            "avg_latency": int(avg_latency),
            "recent_errors": recent_errors,
            "sim_ts": latest_sim_ts,
            "real_ts": latest_real_ts,
        }


def format_actors(actors) -> str:
    """Format actors list nicely."""
    if not actors:
        return "-"
    if isinstance(actors, str):
        import json
        actors = json.loads(actors)
    return ", ".join(a.replace("npc_", "") for a in actors[:3])


def format_time(ts) -> str:
    """Format timestamp for display."""
    if not ts:
        return "-"
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return ts.strftime("%H:%M:%S")


def truncate(text: str, max_len: int = 50) -> str:
    """Truncate text with ellipsis."""
    if not text:
        return ""
    text = text.replace("\n", " ")
    if len(text) > max_len:
        return text[:max_len-1] + "…"
    return text


def create_events_table(events: list) -> Table:
    """Create a Rich table for events."""
    table = Table(title="Events", box=None, expand=True)
    table.add_column("Type", width=18)
    table.add_column("Who", width=8)
    table.add_column("Where", width=10)

    for event in events:
        event_id, event_type, actors, targets, place_id, sim_ts, ts, payload = event

        color = EVENT_COLORS.get(event_type, "white")
        type_text = Text(event_type, style=color)

        table.add_row(
            type_text,
            format_actors(actors),
            (place_id or "-").replace("place_", ""),
        )

    return table


def create_posts_table(posts: list) -> Table:
    """Create a Rich table for posts."""
    table = Table(title="Recent Posts", box=None, expand=True)
    table.add_column("Ch", width=4)
    table.add_column("Who", width=8)
    table.add_column("Text", no_wrap=False)

    for post in posts:
        post_id, author_id, channel, text, tone, created_at, source_event_id = post

        ch_color = CHANNEL_COLORS.get(channel, "white")
        ch_short = channel[:4] if channel else "?"

        table.add_row(
            Text(ch_short, style=ch_color),
            author_id.replace("npc_", "").replace("NPC_", "") if author_id else "-",
            text or "",
        )

    return table


# Decision action colors
ACTION_COLORS = {
    "IGNORE": "dim",
    "POST_FEED": "bright_blue",
    "POST_CHAT": "bright_cyan",
    "REPLY": "bright_green",
}

EMOTION_EMOJI = {
    "curious": "🤔",
    "happy": "😊",
    "annoyed": "😤",
    "worried": "😟",
    "neutral": "😐",
    "amused": "😄",
    "proud": "😎",
    "sad": "😢",
}


def create_decisions_table(decisions: list, show_all: bool = False) -> Table:
    """Create a Rich table for decisions."""
    table = Table(title="Gemini Decisions (5min)", box=None, expand=True)
    table.add_column("Who", width=7)
    table.add_column("Stimulus", width=12)
    table.add_column("Action", width=9)
    table.add_column("Emo", width=3)
    table.add_column("Draft", no_wrap=False)
    table.add_column("ms", width=5, justify="right")

    for dec in decisions:
        (job_id, npc_id, stimulus_type, action, intent, emotion,
         draft, reasoning, latency_ms, error, processed_at) = dec

        # Skip IGNORE unless show_all
        if not show_all and action == "IGNORE":
            continue

        action_color = ACTION_COLORS.get(action, "white")
        emo = EMOTION_EMOJI.get(emotion, "")

        # Format latency
        lat_str = str(latency_ms) if latency_ms else "-"
        if error:
            lat_str = Text("ERR", style="red")

        table.add_row(
            npc_id.replace("npc_", "") if npc_id else "-",
            truncate(stimulus_type or "", 12),
            Text(action, style=action_color),
            emo,
            truncate(draft or "", 40),
            lat_str if isinstance(lat_str, Text) else lat_str,
        )

    return table


def create_stats_panel(stats: dict, services: dict) -> Panel:
    """Create a stats panel with service status."""
    sim_time = format_time(stats["sim_ts"]) if stats["sim_ts"] else "-"
    real_time = format_time(stats["real_ts"]) if stats["real_ts"] else "-"

    # Format service status
    svc_parts = []
    svc_order = ["db", "redis", "llm", "gateway", "api", "engine", "decision", "workers"]
    for name in svc_order:
        if name in services:
            svc = services[name]
            if svc["ok"] and svc["status"] == "ok":
                svc_parts.append(f"[green]●[/]{name}")
            elif svc["ok"]:  # running but unhealthy
                svc_parts.append(f"[yellow]●[/]{name}")
            else:
                svc_parts.append(f"[red]●[/]{name}")

    svc_line = " ".join(svc_parts)

    # Decision stats
    dec_active = stats.get("recent_active", 0)
    dec_latency = stats.get("avg_latency", 0)
    dec_errors = stats.get("recent_errors", 0)
    dec_color = "green" if dec_errors == 0 else "red"

    content = (
        f"[bold]Events:[/] {stats['events']}  "
        f"[bold]Posts:[/] {stats['posts']}  "
        f"[bold]Decisions:[/] {stats.get('decisions', 0)}  "
        f"[bold]Sim:[/] {sim_time}  "
        f"[bold]Real:[/] {real_time}\n"
        f"[bold]Gemini 5min:[/] [{dec_color}]{dec_active} active[/] | "
        f"~{dec_latency}ms | "
        f"{'[red]' + str(dec_errors) + ' errors[/]' if dec_errors else '[green]no errors[/]'}  "
        f"{svc_line}"
    )
    return Panel(content, title="[bold cyan]KOIVULAHTI[/]", border_style="cyan")


def create_display(conn, args) -> Layout:
    """Create the full display layout."""
    stats = fetch_stats(conn)
    services = get_services_status()
    events = fetch_recent_events(
        conn,
        limit=args.limit,
        npc_filter=args.npc,
        type_filter=args.type,
    )
    decisions = fetch_recent_decisions(
        conn,
        limit=args.limit * 2,  # More decisions since we filter IGNORE
        npc_filter=args.npc,
        action_filter=getattr(args, 'action', None),
    )
    posts = fetch_recent_posts(
        conn,
        limit=args.limit // 2,
        npc_filter=args.npc,
        channel_filter=args.channel,
    )

    layout = Layout()
    layout.split_column(
        Layout(create_stats_panel(stats, services), size=5),
        Layout(name="main"),
    )

    # Show pipeline: Events → Decisions → Posts
    show_all_decisions = getattr(args, 'all_decisions', False)
    layout["main"].split_row(
        Layout(create_events_table(events), ratio=1),
        Layout(create_decisions_table(decisions, show_all=show_all_decisions), ratio=2),
        Layout(create_posts_table(posts), ratio=2),
    )

    return layout


def run_once(args):
    """Run once and print results."""
    conn = get_db_connection()
    try:
        layout = create_display(conn, args)
        console.print(layout)
    finally:
        conn.close()


def run_live(args):
    """Run in live mode with auto-refresh."""
    conn = get_db_connection()
    try:
        with Live(create_display(conn, args), refresh_per_second=0.5, console=console) as live:
            while True:
                time.sleep(args.interval)
                live.update(create_display(conn, args))
    except KeyboardInterrupt:
        console.print("\n[dim]Stopped.[/]")
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Koivulahti Village Monitor - Live activity feed"
    )
    parser.add_argument(
        "--live", "-l",
        action="store_true",
        help="Live mode with auto-refresh"
    )
    parser.add_argument(
        "--interval", "-i",
        type=float,
        default=2.0,
        help="Refresh interval in seconds (default: 2)"
    )
    parser.add_argument(
        "--limit", "-n",
        type=int,
        default=15,
        help="Number of items to show (default: 15)"
    )
    parser.add_argument(
        "--npc",
        type=str,
        help="Filter by NPC (e.g., npc_sanni or just sanni)"
    )
    parser.add_argument(
        "--type", "-t",
        type=str,
        help="Filter by event type (e.g., SMALL_TALK)"
    )
    parser.add_argument(
        "--channel", "-c",
        type=str,
        help="Filter posts by channel (FEED, CHAT, NEWS)"
    )
    parser.add_argument(
        "--action", "-a",
        type=str,
        help="Filter decisions by action (IGNORE, POST_FEED, POST_CHAT, REPLY)"
    )
    parser.add_argument(
        "--all-decisions",
        action="store_true",
        dest="all_decisions",
        help="Show all decisions including IGNORE"
    )

    args = parser.parse_args()

    # Normalize NPC filter
    if args.npc and not args.npc.startswith("npc_"):
        args.npc = f"npc_{args.npc}"

    if args.live:
        run_live(args)
    else:
        run_once(args)


if __name__ == "__main__":
    main()
