"""Mojo Operational Tools: Ticket Lifecycle Management and Output Sanitization."""

from std.python import Python, PythonObject
from app_mojo.db import get_connection

def sanitize_output(output: String, max_length: Int = 2500) -> String:
    """Safeguards agent context windows against unbounded tool output."""
    var total_bytes = output.byte_length()
    if total_bytes > max_length:
        var head_len = (max_length - 50) // 2
        var tail_len = head_len
        var prefix = output[byte=0:head_len]
        var suffix = output[byte=(total_bytes - tail_len):total_bytes]
        return prefix + "\n...[OUTPUT TRUNCATED BY MCP GUARDIAN]...\n" + suffix
    return output

def create_support_ticket(ticket_id: String, email: String, summary: String, custom_db_path: PythonObject = Python.none()) raises -> String:
    """Inserts a verified customer support ticket into the operational database."""
    var conn = get_connection(custom_db_path)
    var cur = conn.cursor()
    try:
        var params = Python.evaluate("[]")
        params.append(ticket_id)
        params.append(email)
        params.append(summary)

        cur.execute(
            """
        INSERT INTO support_tickets (ticket_id, customer_email, issue_summary)
        VALUES (?, ?, ?)
        """,
            params,
        )
        conn.commit()
        conn.close()
        return "Ticket " + ticket_id + " created successfully."
    except e:
        conn.close()
        return "Error creating ticket: " + String(e)

def get_support_ticket(ticket_id: String, custom_db_path: PythonObject = Python.none()) raises -> String:
    """Fetches support ticket details and current status by ID."""
    var conn = get_connection(custom_db_path)
    var cur = conn.cursor()

    var params = Python.evaluate("[]")
    params.append(ticket_id)

    cur.execute(
        """
    SELECT ticket_id, customer_email, issue_summary, status, created_at
    FROM support_tickets
    WHERE ticket_id = ?
    """,
        params,
    )
    var row = cur.fetchone()
    conn.close()

    if row is None:
        return "Ticket '" + ticket_id + "' not found."

    return (
        "Ticket ID: "
        + String(row[0])
        + "\nCustomer Email: "
        + String(row[1])
        + "\nSummary: "
        + String(row[2])
        + "\nStatus: "
        + String(row[3])
        + "\nCreated At: "
        + String(row[4])
    )

def update_ticket_status(ticket_id: String, status: String, custom_db_path: PythonObject = Python.none()) raises -> String:
    """Updates operational status of an existing ticket."""
    var conn = get_connection(custom_db_path)
    var cur = conn.cursor()
    try:
        var params = Python.evaluate("[]")
        params.append(status)
        params.append(ticket_id)

        cur.execute(
            """
        UPDATE support_tickets
        SET status = ?
        WHERE ticket_id = ?
        """,
            params,
        )
        conn.commit()
        var updated = cur.rowcount
        conn.close()
        if updated == 0:
            return "Ticket " + ticket_id + " not found."
        return "Ticket " + ticket_id + " status updated to '" + status + "'."
    except e:
        conn.close()
        return "Error updating ticket: " + String(e)

def list_support_tickets(status: String = "", custom_db_path: PythonObject = Python.none()) raises -> String:
    """Lists tickets, optionally filtered by status."""
    var conn = get_connection(custom_db_path)
    var cur = conn.cursor()
    if status.strip().byte_length() > 0:
        var params = Python.evaluate("[]")
        params.append(status.strip())
        cur.execute(
            """
        SELECT ticket_id, customer_email, issue_summary, status, created_at
        FROM support_tickets
        WHERE status = ?
        ORDER BY created_at DESC
        """,
            params,
        )
    else:
        cur.execute(
            """
        SELECT ticket_id, customer_email, issue_summary, status, created_at
        FROM support_tickets
        ORDER BY created_at DESC
        """
        )

    var rows = cur.fetchall()
    conn.close()

    if not rows:
        return "No support tickets found."

    var lines = Python.evaluate("[]")
    for r in rows:
        var line = "[" + String(r[0]) + "] (" + String(r[3]) + ") - " + String(r[1]) + ": " + String(r[2])
        lines.append(line)

    var joiner = Python.evaluate("lambda items: '\\n'.join(items)")
    return String(joiner(lines))
