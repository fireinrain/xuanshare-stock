"""生成交易日历 JSON 文件，供前端判断交易日/休市。"""

import json
import datetime
from pathlib import Path

try:
    import baostock as bs
except ImportError:
    print("请先安装 baostock: pip install baostock pandas")
    exit(1)


def main():
    lg = bs.login()
    if lg.error_code != "0":
        print(f"[ERROR] baostock 登录失败: {lg.error_msg}")
        exit(1)

    this_year = datetime.date.today().year
    next_year = this_year + 1
    start = f"{this_year}-01-01"
    end = f"{next_year}-12-31"

    print(f"正在获取交易日历: {start} ~ {end} ...")
    rs = bs.query_trade_dates(start_date=start, end_date=end)
    df = rs.get_data()

    trading_days = sorted(df[df["is_trading_day"] == "1"]["calendar_date"].tolist())

    bs.logout()

    output_dir = Path(__file__).resolve().parent.parent / "src" / "data"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "trading_calendar.json"

    output_file.write_text(
        json.dumps({"tradingDays": trading_days, "updatedAt": datetime.date.today().isoformat()}, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"✅ 已生成 {output_file}")
    print(f"   交易日数量: {len(trading_days)} 天")
    print(f"   范围: {trading_days[0]} ~ {trading_days[-1]}")


if __name__ == "__main__":
    main()
