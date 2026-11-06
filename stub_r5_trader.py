"""Stub R5 trader for Monte Carlo smoke-testing. Quotes nothing."""
from datamodel import TradingState

class Trader:
    def run(self, state: TradingState):
        return {}, 0, ""
