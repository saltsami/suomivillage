#!/usr/bin/env python3
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
from datetime import datetime, timezone
from typing import Optional

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

        return {
            "events": event_count,
            "posts": post_count,
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
    table = Table(title="Recent Events", box=None, expand=True)
    table.add_column("Time", style="dim", width=8)
    table.add_column("Type", width=22)
    table.add_column("Who", width=12)
    table.add_column("Where", width=15)

    for event in events:
        event_id, event_type, actors, targets, place_id, sim_ts, ts, payload = event

        color = EVENT_COLORS.get(event_type, "white")
        type_text = Text(event_type, style=color)

        table.add_row(
            format_time(sim_ts),
            type_text,
            format_actors(actors),
            (place_id or "-").replace("place_", ""),
        )

    return table


def create_posts_table(posts: list) -> Table:
    """Create a Rich table for posts."""
    table = Table(title="Recent Posts", box=None, expand=True)
    table.add_column("Time", style="dim", width=8)
    table.add_column("Ch", width=4)
    table.add_column("Author", width=10)
    table.add_column("Text", width=45)

    for post in posts:
        post_id, author_id, channel, text, tone, created_at, source_event_id = post

        ch_color = CHANNEL_COLORS.get(channel, "white")
        ch_short = channel[:4] if channel else "?"

        table.add_row(
            format_time(created_at),
            Text(ch_short, style=ch_color),
            author_id.replace("npc_", "") if author_id else "-",
            truncate(text, 45),
        )

    return table


def create_stats_panel(stats: dict) -> Panel:
    """Create a stats panel."""
    sim_time = format_time(stats["sim_ts"]) if stats["sim_ts"] else "-"
    real_time = format_time(stats["real_ts"]) if stats["real_ts"] else "-"

    content = (
        f"[bold]Events:[/] {stats['events']}  "
        f"[bold]Posts:[/] {stats['posts']}  "
        f"[bold]Sim:[/] {sim_time}  "
        f"[bold]Real:[/] {real_time}"
    )
    return Panel(content, title="[bold cyan]KOIVULAHTI[/]", border_style="cyan")


def create_display(conn, args) -> Layout:
    """Create the full display layout."""
    stats = fetch_stats(conn)
    events = fetch_recent_events(
        conn,
        limit=args.limit,
        npc_filter=args.npc,
        type_filter=args.type,
    )
    posts = fetch_recent_posts(
        conn,
        limit=args.limit // 2,
        npc_filter=args.npc,
        channel_filter=args.channel,
    )

    layout = Layout()
    layout.split_column(
        Layout(create_stats_panel(stats), size=3),
        Layout(name="main"),
    )
    layout["main"].split_row(
        Layout(create_events_table(events)),
        Layout(create_posts_table(posts)),
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
