"""Run with: .venv/bin/streamlit run app.py"""
from dataclasses import asdict
from datetime import datetime
import json
from uuid import uuid4
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.express as px
import streamlit as st

from matrixlab.analytics import analyze, holdout_curve, performance
from matrixlab.config import Settings
from matrixlab.data import (DOC_COLUMNS, PRICE_COLUMNS, DataError, data_quality,
                            read_documents, read_prices, validate_documents, validate_prices)
from matrixlab.research import ResearchUnavailable, screen
from matrixlab.trading import Broker, Order, TradingError, rebalance_orders

st.set_page_config(page_title="Matrix Research Lab", page_icon="◈", layout="wide")
settings = Settings.load()
settings.data_dir.mkdir(parents=True, exist_ok=True)
today = datetime.now(ZoneInfo("America/New_York")).date()
st.markdown("""<style>
.block-container {padding-top:2.2rem; max-width:1450px;}
div[data-testid="stMetric"] {background:#131f32;border:1px solid #24354c;padding:18px;border-radius:12px;}
h1 {letter-spacing:-0.04em;} div[data-testid="stCaptionContainer"] {color:#94a9c2;}
.eyebrow {color:#4fdbb0;font-size:.8rem;letter-spacing:.16em;margin-bottom:.4rem;}
</style><div class="eyebrow">MATRIX / RESEARCH WORKSPACE</div>""", unsafe_allow_html=True)
st.title("让研究有依据，让风险可计算")
st.caption("矩阵原理及应用 · JEVDB股票研究与模拟交易原型")

with st.sidebar:
    st.header("研究工作区")
    st.caption("美股 · USD · 日线 · 单个本地模拟账户")
    st.info("统一复权价格；整数模拟份额。模拟撮合使用下一交易日开盘价。")
    with st.expander("导入本地CSV"):
        kind = st.selectbox("数据类型", ["行情", "公司资料"], key="import_kind")
        upload = st.file_uploader("选择CSV（最大20MB）", type=["csv"])
        columns = PRICE_COLUMNS if kind == "行情" else DOC_COLUMNS
        st.download_button("下载字段模板", pd.DataFrame(columns=columns).to_csv(index=False),
                           file_name="prices-template.csv" if kind == "行情" else "documents-template.csv", mime="text/csv")
        if st.button("校验并保存", disabled=upload is None):
            try:
                frame = pd.read_csv(upload)
                frame = validate_prices(frame) if kind == "行情" else validate_documents(frame)
                target = settings.data_dir / ("prices.csv" if kind == "行情" else "documents.csv")
                if kind == "行情" and (settings.data_dir / "paper.sqlite3").exists() and Broker(settings.data_dir / "paper.sqlite3").exists():
                    raise DataError("本工作区已有模拟账本。请使用新的MATRIX_DATA_DIR导入另一份行情快照。")
                part = target.with_suffix(".csv.part")
                frame.to_csv(part, index=False)
                part.replace(target)
                st.success(f"已保存{len(frame)}行。")
                st.rerun()
            except (ValueError, OSError) as exc:
                st.error(str(exc))
    st.caption("原始数据、资料、凭证和交易账本只保存本地。")


@st.cache_data
def load_prices(path, modified):
    return read_prices(path)


price_path = settings.data_dir / "prices.csv"
if not price_path.exists():
    st.info("先下载真实行情，或从左侧导入CSV。程序不会生成示例行情。")
    st.code(".venv/bin/python -m matrixlab.cli fetch", language="bash")
    st.stop()
try:
    prices = load_prices(str(price_path), price_path.stat().st_mtime_ns)
except (DataError, OSError) as exc:
    st.error(str(exc))
    st.stop()

universe = sorted(prices.symbol.unique())
days = sorted(prices.date.dt.date.unique())
c1, c2, c3, c4 = st.columns(4)
c1.metric("股票池", f"{len(universe)}只")
c2.metric("真实日线", f"{len(prices):,}条")
c3.metric("行情截至", str(days[-1]))
c4.metric("模型连接", "已配置凭证" if settings.credential_available else "待配置API")
overview, research, matrix, paper = st.tabs(["01 数据与依据", "02 公司研究", "03 矩阵与组合", "04 模拟交易"])

with overview:
    st.subheader("先检查数据，再解释结果")
    st.caption("数据快照包含来源与获取时间；历史资料按可用时间过滤。供应商的历史价格可能被修订。")
    st.dataframe(data_quality(prices), hide_index=True, width="stretch")
    chosen = st.selectbox("查看行情", universe, key="chart_symbol")
    history = prices.loc[prices.symbol.eq(chosen)]
    fig = px.line(history, x="date", y="close", title=f"{chosen} · 复权收盘价", color_discrete_sequence=["#31d4a4"])
    fig.update_layout(height=320, margin=dict(l=0, r=0, t=40, b=0), yaxis_title="USD / 模拟份额")
    st.plotly_chart(fig, width="stretch")
    with st.expander("查看原始行与来源"):
        st.dataframe(history.tail(30), hide_index=True, width="stretch")
    st.warning("模拟份额采用总回报复权价；不再次调整拆股或发放股息。它用于课程比较，不还原真实历史股数、税费或结算制度。")

with research:
    st.subheader("从资料中筛选公司")
    st.caption("离线模式按词匹配；JEVDB模式实际调用语义数据库。两种结果分别标记。")
    docs_path = settings.data_dir / "documents.csv"
    docs = None
    if docs_path.exists():
        try:
            docs = read_documents(docs_path)
        except DataError as exc:
            st.info(str(exc))
    if docs is None:
        st.info("尚无有效公司资料。运行fetch获取当前简介，或导入包含available_at及来源的资料CSV。")
    else:
        with st.form("research_form"):
            query = st.text_area("研究条件", "cloud software", help="离线模式以空格拆词，任意词匹配；JEVDB模式支持自然语言条件。")
            l, r = st.columns(2)
            research_day = l.date_input("资料可用日期（纽约日末）", value=today, key="research_day")
            mode_label = r.selectbox("筛选方式", ["离线关键词基线", "JEVDB语义查询"])
            limit = st.slider("最多处理的资料条数", 1, 200, 100)
            submitted = st.form_submit_button("检索并保留依据", type="primary")
        if submitted:
            try:
                with st.spinner("正在查询资料…"):
                    run = screen(docs, query, research_day, settings,
                                 "keyword" if mode_label.startswith("离线") else "jevdb", limit)
                    run.save(settings.data_dir / "research_runs")
                    st.session_state.research_run = run
            except (DataError, ResearchUnavailable) as exc:
                st.session_state.pop("research_run", None)
                st.error(str(exc))
        run = st.session_state.get("research_run")
        if run:
            st.success(f"{run.backend} · 检查{run.inputs}条资料 · 命中{len(run.matches)}条 · {run.elapsed_seconds:.3f}秒")
            results = run.frame()
            if not results.empty:
                st.dataframe(results[["symbol", "title", "available_at", "source_url", "text"]], hide_index=True, width="stretch")
                if st.button("将这些公司用于组合研究"):
                    selected = sorted(set(results.symbol) & set(universe))
                    if len(selected) < 2:
                        st.warning("至少需要两只有行情的公司。")
                    else:
                        st.session_state.portfolio_symbols = selected
                        st.session_state.study_day = pd.Timestamp(run.asof).date()
                        st.session_state.selection_asof = run.asof
                        st.success("已带入“矩阵与组合”；研究日期不会早于筛选资料的可用日期。")
            st.download_button("导出本次研究记录", json.dumps(asdict(run), ensure_ascii=False, indent=2, default=str),
                               file_name=f"research-{run.run_id}.json", mime="application/json")
        st.caption("在线获取的当前公司简介以获取时间作为available_at；它不能用于更早的历史选股。")

with matrix:
    st.subheader("用矩阵解释组合风险")
    if "portfolio_symbols" not in st.session_state:
        st.session_state.portfolio_symbols = universe
    if "study_day" not in st.session_state:
        st.session_state.study_day = days[int(len(days) * 0.7)]
    selected = st.multiselect("组合股票", universe, key="portfolio_symbols")
    left, middle, right = st.columns(3)
    study_day = left.date_input("研究日期（拟合数据截至此日）", key="study_day", min_value=days[0], max_value=max(today, days[-1]))
    lookback = middle.number_input("回看收益率条数", min_value=60, max_value=1260, value=252, step=21)
    alpha = right.slider("协方差收缩系数α", 0.0, 1.0, 0.05, 0.01)
    if st.session_state.get("selection_asof"):
        st.caption("公司筛选依据日期：" + st.session_state.selection_asof)
        if st.button("清除筛选绑定，手动研究股票池"):
            st.session_state.pop("selection_asof", None)
            st.rerun()
    signature = (tuple(selected), str(study_day), lookback, alpha, price_path.stat().st_mtime_ns)
    if st.button("计算矩阵与最小方差组合", type="primary"):
        try:
            if st.session_state.get("selection_asof") and str(study_day) < st.session_state.selection_asof:
                raise DataError("研究日期早于选股资料可用日期，存在未来信息，已停止计算。")
            risk = analyze(prices, selected, study_day, int(lookback), alpha)
            st.session_state.risk = risk
            st.session_state.risk_signature = signature
        except DataError as exc:
            st.error(str(exc))
    risk = st.session_state.get("risk") if st.session_state.get("risk_signature") == signature else None
    if risk:
        l, m, r = st.columns(3)
        l.metric("年化波动率（样本内）", f"{risk.volatility:.2%}")
        m.metric("有效收益率样本", len(risk.returns))
        r.metric("正则化后条件数", f"{risk.condition_after:.2f}")
        a, b = st.columns([1, 1.7])
        with a:
            st.dataframe(risk.weights.rename("目标权重").to_frame().style.format("{:.2%}"), width="stretch")
            st.download_button("导出目标权重", risk.weights.to_csv(), file_name="weights.csv")
        with b:
            fig = px.imshow(risk.covariance, color_continuous_scale="Teal", title="年化协方差矩阵")
            fig.update_layout(height=340, margin=dict(l=0, r=0, t=40, b=0))
            st.plotly_chart(fig, width="stretch")
        with st.expander("矩阵推导与数值诊断"):
            st.latex(r"\Sigma=\frac{252}{T-1}X^T X,\quad\Sigma_\alpha=(1-\alpha)\Sigma+\alpha\frac{\mathrm{tr}(\Sigma)}{N}I")
            st.latex(r"\min_w\;w^T\Sigma_\alpha w\quad\mathrm{s.t.}\quad\mathbf{1}^T w=1,\; w\geq0")
            st.write(f"原矩阵条件数：{risk.condition_before:.4g}；最小特征值：{risk.eigenvalues.min():.6g}；因缺失排除{risk.excluded_rows}行。")
            st.caption("协方差为Gram矩阵，理论上半正定；收缩改善病态性。目标权重通过带约束数值优化得到。")
            st.dataframe(risk.regularized, width="stretch")
        st.markdown("**样本外比较：次日复权开盘建仓，之后持有，权重随价格漂移。**")
        try:
            curve = holdout_curve(prices, risk.weights, study_day)
            fig = px.line(curve, color_discrete_sequence=["#31d4a4", "#8ca3c5"])
            fig.update_layout(height=320, yaxis_title="净值", legend_title_text="", margin=dict(l=0, r=0, t=15, b=0))
            st.plotly_chart(fig, width="stretch")
            st.dataframe(performance(curve).style.format("{:.2%}"), width="stretch")
            st.caption("首笔总成本默认15bp；此比较使用可分份额模型。离散份额与逐笔费用以模拟账本为准。")
        except DataError as exc:
            st.info(str(exc))
    else:
        st.info("选择股票和研究日期后计算；输入变更后需要重新计算。")

with paper:
    st.subheader("把组合变成可追溯的模拟订单")
    broker = Broker(settings.data_dir / "paper.sqlite3")
    if not broker.exists():
        with st.form("account_form"):
            start_day = st.selectbox("模拟起始交易日", days, index=int(len(days) * 0.7))
            cash = st.number_input("初始现金（USD）", min_value=100.0, max_value=1e8, value=100000.0)
            l, r = st.columns(2)
            commission = l.number_input("手续费（bp）", 0.0, 1000.0, 10.0)
            slippage = r.number_input("滑点（bp）", 0.0, 1000.0, 5.0)
            if st.form_submit_button("创建本地模拟账户", type="primary"):
                try:
                    broker.initialize(cash, start_day, commission, slippage)
                    st.rerun()
                except TradingError as exc:
                    st.error(str(exc))
    else:
        account, positions, snapshots, orders = broker.state()
        l, m, r = st.columns(3)
        l.metric("可用现金", f"${account['cash']:,.2f}")
        m.metric("账户权益", f"${snapshots.iloc[-1].equity:,.2f}")
        r.metric("模拟日期", account["clock"])
        st.caption(f"下一交易日复权开盘撮合；手续费{account['commission_bps']:g}bp，滑点{account['slippage_bps']:g}bp；现金与持仓原子更新。")
        st.dataframe(positions, hide_index=True, width="stretch")
        if "request_id" not in st.session_state:
            st.session_state.request_id = str(uuid4())
        with st.form("order_form"):
            l, m, r = st.columns(3)
            symbol = l.selectbox("股票", universe, key="order_symbol")
            side = m.selectbox("方向", ["BUY", "SELL"])
            quantity = r.number_input("整数模拟份额", min_value=1, max_value=1000000000, value=1, step=1)
            buy = st.form_submit_button("提交并推进至下一交易日", type="primary")
        if buy:
            try:
                fills = broker.execute([Order(symbol, side, int(quantity))], account["clock"], prices, st.session_state.request_id)
                st.session_state.last_fills = fills
                st.session_state.request_id = str(uuid4())
                st.rerun()
            except TradingError as exc:
                st.error(str(exc))
        # The displayed quote only uses the current clock; the next open is never previewed.
        if risk and pd.Timestamp(study_day).date() == pd.Timestamp(account["clock"]).date():
            try:
                ticket = rebalance_orders(prices, risk.weights, study_day, float(snapshots.iloc[-1].equity), positions)
                st.markdown("**按目标权重调仓：按当日收盘估算份额，保留5%现金。**")
                st.dataframe(pd.DataFrame([asdict(o) for o in ticket]), hide_index=True, width="stretch")
                if st.button("确认整批调仓（次日开盘）", disabled=not ticket):
                    fills = broker.execute(ticket, study_day, prices, st.session_state.request_id)
                    st.session_state.last_fills = fills
                    st.session_state.request_id = str(uuid4())
                    st.rerun()
            except TradingError as exc:
                st.error(str(exc))
        else:
            st.caption("让矩阵研究日期与模拟日期一致，可生成整批调仓订单。")
        future_days = [d for d in days if str(d) > account["clock"]]
        if future_days:
            with st.form("advance_form"):
                target_day = st.selectbox("向前观察至", future_days)
                if st.form_submit_button("推进日期并重新估值"):
                    try:
                        broker.advance(prices, target_day)
                        st.rerun()
                    except TradingError as exc:
                        st.error(str(exc))
        if st.session_state.get("last_fills"):
            st.success("成交已保存。")
            st.dataframe(pd.DataFrame(st.session_state.last_fills), hide_index=True, width="stretch")
        if len(snapshots) > 1:
            st.plotly_chart(px.line(snapshots, x="date", y="equity", title="模拟账户权益"), width="stretch")
        with st.expander("全部成交记录", expanded=True):
            st.dataframe(orders, hide_index=True, width="stretch")
            st.download_button("导出成交CSV", orders.to_csv(index=False), file_name="orders.csv", mime="text/csv")
