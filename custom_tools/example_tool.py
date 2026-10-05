"""Example Custom Tool Plugin for ROMS.

To add new MCP tools to ROMS, simply create a python file in custom_tools/
and define a register_tools(mcp) function.
"""

def register_tools(mcp):
    """Registers custom tools directly into the ROMS FastMCP engine."""

    @mcp.tool()
    def calculate_refund_amount(item_price: float, return_shipping_fee: float = 0.0) -> str:
        """Calculates final refund amount after deducting return shipping."""
        total = max(0.0, item_price - return_shipping_fee)
        return f"Final refundable amount: ${total:.2f} (Original: ${item_price:.2f}, Shipping Fee: ${return_shipping_fee:.2f})"
