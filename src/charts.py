import matplotlib.pyplot as plt

def plot_im_comparison(im_bilateral: float, im_ccp: float, savepath: str):
    labels = ["Bilateral IM", "CCP IM"]
    vals = [im_bilateral, im_ccp]
    fig = plt.figure()
    plt.bar(labels, vals)
    for i, v in enumerate(vals):
        plt.text(i, v, f"${v:,.0f}", ha="center", va="bottom")
    plt.title("Initial Margin Comparison")
    plt.ylabel("USD")
    fig.savefig(savepath, bbox_inches="tight")
    plt.close(fig)

def plot_vm_paths(vm_bil_series, vm_ccp_series, savepath: str):
    fig = plt.figure()
    vm_bil_series.cumsum().plot(label="Bilateral VM (cum)")
    vm_ccp_series.cumsum().plot(label="CCP VM (cum)")
    plt.legend()
    plt.title("Cumulative VM Outflows")
    plt.ylabel("USD")
    plt.xlabel("Date")
    fig.savefig(savepath, bbox_inches="tight")
    plt.close(fig)

def plot_sample_trades(trades_df, savepath: str):
    """
    Plots sample trade exposures or MTM values over time.
    Expects a DataFrame with columns like ['date', 'trade_id', 'mtm'].
    """
    fig = plt.figure()

    for trade_id, df_trade in trades_df.groupby('trade_id'):
        plt.plot(df_trade['date'], df_trade['mtm'], label=f"Trade {trade_id}")

    plt.legend()
    plt.title("Sample Trade MTM Paths")
    plt.xlabel("Date")
    plt.ylabel("Mark-to-Market Value (USD)")
    fig.savefig(savepath, bbox_inches="tight")
    plt.close(fig)
