class PaymentService:
    """Coordinates payment attempts with the external payment provider."""

    def processPayment(self, order_id: str, amount_cents: int) -> str:
        """Return a provider transaction ID or raise PaymentFailed."""
        provider_response = self.provider.charge(order_id, amount_cents)
        if not provider_response.ok:
            raise PaymentFailed(order_id)
        return provider_response.transaction_id

    def refundPayment(self, transaction_id: str) -> None:
        self.provider.refund(transaction_id)
