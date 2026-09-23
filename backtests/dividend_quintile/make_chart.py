import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

df = pd.read_csv("/tmp/claude-0/-home-user-Robinhood/9cd955bf-712e-5400-90f6-198dab301530/scratchpad/cumulative_returns.csv", index_col=0, parse_dates=True)
growth = df * 1000  # growth of $1,000

fig, ax = plt.subplots(figsize=(11, 6.5))
colors = {"Q1": "#9CA3AF", "Q2": "#2563EB", "Q3": "#9CA3AF", "Q4": "#9CA3AF", "Q5": "#9CA3AF", "SPY": "#111827"}
widths = {"Q2": 3.0, "SPY": 2.2}
for col in ["Q1", "Q3", "Q4", "Q5", "SPY", "Q2"]:
    if col not in growth.columns:
        continue
    ax.plot(growth.index, growth[col], label=("2nd Quintile" if col == "Q2" else col),
            color=colors.get(col, "#999"), linewidth=widths.get(col, 1.3),
            alpha=1.0 if col in ("Q2", "SPY") else 0.6)

ax.set_title("S&P 500 Dividend-Yield Quintile Backtest\nMonthly Rebalance, Dividends Reinvested", fontsize=14, fontweight="bold")
ax.set_ylabel("Growth of $1,000")
ax.set_yscale("log")
ax.legend(loc="upper left", frameon=False)
ax.grid(alpha=0.3)
fig.tight_layout()
fig.savefig("/tmp/claude-0/-home-user-Robinhood/9cd955bf-712e-5400-90f6-198dab301530/scratchpad/backtest_chart.png", dpi=150)
print("saved chart")
