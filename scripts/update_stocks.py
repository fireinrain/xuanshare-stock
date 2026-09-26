#!/usr/bin/env python3
"""
A股股票池自动更新脚本 - 去重合并模式
数据来源：东方财富 API（主）→ akshare（备1）→ baostock（备2）
每月运行一次，以去重方式将新股票增量合并到现有股票池
"""

import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import requests as http_lib
    HAS_REQUESTS = True
except ImportError:
    import urllib.request
    import urllib.error
    HAS_REQUESTS = False

# ============================================================
# 配置
# ============================================================

BATCH_SIZE = 1000
OUTPUT_DIR = "src/data"
PAGE_SIZE = 100
MAX_PAGES = 100

EASTMONEY_URL = "https://push2.eastmoney.com/api/qt/clist/get"

BASE_PARAMS = {
    "pz": str(PAGE_SIZE),
    "po": "1",
    "np": "1",
    "ut": "bd1d9ddb04089700cf9c27f6f7426281",
    "fltt": "2",
    "invt": "2",
    "fid": "f12",
    "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
    "fields": "f12,f14,f26,f100",
}

# ============================================================
# 行业关键词 → 五行 映射
# ============================================================

WUXING_RULES = [
    ("metal", ["银行", "保险", "证券", "非银金融", "信托", "期货", "金融控股",
               "多元金融"]),
    ("metal", ["有色金属", "贵金属", "黄金", "白银", "钢铁", "铅锌", "铜", "铝",
               "钛", "钴", "镍", "钨", "钼", "稀土", "锂矿", "铁矿石", "特钢",
               "金属新材料", "磁性材料", "粉末冶金", "小金属", "工业金属"]),
    ("metal", ["汽车", "商用车", "乘用车", "摩托车", "底盘", "发动机", "变速箱",
               "汽车零部件", "轮胎", "轮毂", "军工", "航天", "航空", "兵器", "船舶",
               "装备", "机械设备", "通用设备", "专用设备", "自动化设备", "机床",
               "工程机械", "重型机械", "仪器仪表", "机器人", "激光", "焊接", "模具",
               "刀具", "量具", "电源设备", "轨交设备"]),
    ("metal", ["电网", "输变电", "变压器", "开关", "电缆", "电线", "光纤光缆",
               "电气设备"]),
    ("wood", ["农业", "林业", "牧业", "渔业", "种植", "养殖", "种业", "饲料",
              "兽药", "农产品加工", "粮油", "糖", "棉花", "橡胶", "宠物食品"]),
    ("wood", ["医药", "生物制品", "中药", "化学制药", "医疗器械", "医疗服务",
              "医药商业", "疫苗", "血液制品", "基因", "细胞", "创新药"]),
    ("wood", ["教育", "出版", "传媒", "广告", "影视", "动漫", "游戏", "数字媒体",
              "文化", "体育", "艺术", "营销", "广电"]),
    ("wood", ["纺织", "服装", "造纸", "家具", "家纺", "印染", "皮革", "羽绒",
              "包装印刷", "文娱用品", "个护用品"]),
    ("water", ["航运", "港口", "机场", "高速公路", "铁路", "物流", "快递",
               "运输", "公交", "地铁", "跨境物流", "航空运输"]),
    ("water", ["贸易", "零售", "批发", "百货", "超市", "便利店", "连锁",
               "电商", "跨境电商", "免税", "供销社", "专业连锁"]),
    ("water", ["饮料", "酿酒", "白酒", "啤酒", "葡萄酒", "黄酒", "乳制品",
               "食品", "调味品", "休闲食品", "预制菜", "旅游", "酒店",
               "餐饮", "景区", "烘焙", "零食"]),
    ("water", ["水务", "水利", "自来水", "污水处理"]),
    ("fire", ["电子", "半导体", "芯片", "集成电路", "PCB", "LED", "显示",
              "光学", "光电子", "传感器", "被动元件", "连接器", "消费电子", "面板"]),
    ("fire", ["通信", "计算机", "互联网", "软件", "IT服务", "云计算",
              "大数据", "人工智能", "网络安全", "区块链", "元宇宙",
              "信息", "电信", "5G", "6G", "卫星通信", "数据中心"]),
    ("fire", ["电力", "光伏", "新能源", "风能", "核能", "氢能", "储能",
              "充电桩", "特高压", "太阳能", "发电", "热电", "水电",
              "火电", "电网调度", "虚拟电厂"]),
    ("fire", ["家电", "白电", "黑电", "小家电", "厨卫电器", "照明", "家电零部件"]),
    ("fire", ["电池", "锂电池", "钠电池", "固态电池", "燃料电池", "电池材料"]),
    ("earth", ["房地产", "住宅", "商业地产", "园区", "物业管理", "房产服务",
               "建筑", "基建", "装修", "装饰", "园林", "工程咨询", "设计",
               "房屋建设"]),
    ("earth", ["建材", "水泥", "玻璃", "陶瓷", "石材", "涂料", "防水",
               "管材", "板材", "耐火材料", "混凝土", "石膏", "玻璃玻纤"]),
    ("earth", ["化工", "化学", "石化", "煤化工", "盐化工", "氟化工",
               "磷化工", "农药", "化肥", "染料", "颜料",
               "塑料", "树脂", "纤维", "胶粘剂", "助剂", "催化剂",
               "碳纤维", "石墨", "炭黑", "化学制品", "化学原料"]),
    ("earth", ["环保", "环境治理", "固废", "危废", "环卫", "大气治理", "土壤修复",
               "碳交易", "公用事业", "燃气", "供热"]),
    ("earth", ["煤炭", "石油", "天然气", "油服", "页岩气", "煤层气",
               "采矿", "矿业", "能源"]),
]

COMPILED_RULES = [
    (wuxing, [re.compile(re.escape(kw)) for kw in keywords])
    for wuxing, keywords in WUXING_RULES
]


# ============================================================
# 读取已有股票数据
# ============================================================

# 匹配一个 StockData 对象的正则: { code: '...', name: '...', ... }
_STOCK_ITEM_RE = re.compile(
    r"\{\s*"
    r"code:\s*'(\d{6})'\s*,\s*"
    r"name:\s*'((?:[^'\\]|\\.)*)'\s*,\s*"
    r"listDate:\s*'([^']*)'\s*,\s*"
    r"sector:\s*'((?:[^'\\]|\\.)*)'\s*,\s*"
    r"wuxing:\s*'(metal|wood|water|fire|earth)'\s*"
    r"\}"
)


def _unescape(s: str) -> str:
    """反转义 TypeScript 字符串中的 \\' 和 \\\\"""
    return s.replace("\\'", "'").replace("\\\\", "\\")


def read_existing_stocks(output_dir: Path) -> dict[str, dict]:
    """
    从现有的 stocks_batch*.ts 文件读取所有已有股票数据。
    返回以 code 为键的字典，已有股票不重复拉取。
    """
    existing: dict[str, dict] = {}
    batch_files = sorted(output_dir.glob("stocks_batch*.ts"))
    if not batch_files:
        print("  未找到已有批次文件，将全量初始化")
        return existing

    for f in batch_files:
        content = f.read_text(encoding="utf-8")
        for m in _STOCK_ITEM_RE.finditer(content):
            code = m.group(1)
            name = _unescape(m.group(2))
            list_date = m.group(3)
            sector = _unescape(m.group(4))
            wuxing = m.group(5)
            existing[code] = {
                "code": code,
                "name": name,
                "listDate": list_date,
                "industry": sector,
                "wuxing": wuxing,
            }

    print(f"  读取已有股票: {len(existing)} 只（来自 {len(batch_files)} 个批次文件）")
    return existing


# ============================================================
# 行业 → 五行映射
# ============================================================

def map_industry_to_wuxing(industry: str) -> str:
    if not industry or industry == "-":
        return "water"
    clean = re.sub(r"[Ⅰ-Ⅻ]+$", "", industry).strip()
    for wuxing, patterns in COMPILED_RULES:
        for pat in patterns:
            if pat.search(clean):
                return wuxing
    print(f"  [WARN] 未匹配到五行: {industry} → 默认 water")
    return "water"


# ============================================================
# 数据源 1: 东方财富 API
# ============================================================

def fetch_page_requests(page: int):
    params = dict(BASE_PARAMS)
    params["pn"] = str(page)

    session = http_lib.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://quote.eastmoney.com/",
    })

    for attempt in range(3):
        try:
            resp = session.get(EASTMONEY_URL, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            if data.get("data"):
                return data["data"].get("diff", []), data["data"].get("total", 0)
        except Exception as e:
            if attempt < 2:
                time.sleep((attempt + 1) * 3)
            else:
                print(f"  [ERROR] 第{page}页请求失败: {e}", file=sys.stderr)
    return [], 0


def fetch_page_urllib(page: int):
    params = dict(BASE_PARAMS)
    params["pn"] = str(page)

    query_string = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{EASTMONEY_URL}?{query_string}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://quote.eastmoney.com/",
    }

    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if data.get("data"):
                return data["data"].get("diff", []), data["data"].get("total", 0)
        except Exception as e:
            if attempt < 2:
                time.sleep((attempt + 1) * 3)
            else:
                print(f"  [ERROR] 第{page}页请求失败: {e}", file=sys.stderr)
    return [], 0


def parse_stock_item_eastmoney(item: dict) -> dict | None:
    code = str(item.get("f12", "")).strip()
    name = str(item.get("f14", "")).strip()
    if not code or not name or not code.isdigit() or len(code) != 6:
        return None

    f26 = item.get("f26", 0)
    list_date = ""
    if f26 and isinstance(f26, (int, float)) and f26 > 0:
        try:
            if f26 > 10000000:
                dt = datetime.fromtimestamp(f26 / 1000, tz=timezone.utc)
                list_date = dt.strftime("%Y-%m-%d")
            else:
                s = str(int(f26))
                if len(s) == 8:
                    list_date = f"{s[:4]}-{s[4:6]}-{s[6:8]}"
        except (ValueError, OSError):
            pass

    industry = str(item.get("f100", "")).strip() or "-"
    wuxing = map_industry_to_wuxing(industry)

    return {
        "code": code,
        "name": name,
        "listDate": list_date,
        "industry": industry,
        "wuxing": wuxing,
    }


def fetch_stocks_eastmoney() -> list[dict] | None:
    fetch_fn = fetch_page_requests if HAS_REQUESTS else fetch_page_urllib
    print(f"数据源 1: 东方财富 API ({'requests' if HAS_REQUESTS else 'urllib'})")

    all_stocks = []
    total = 0

    for page in range(1, MAX_PAGES + 1):
        items, total = fetch_fn(page)
        if not items:
            break

        for item in items:
            parsed = parse_stock_item_eastmoney(item)
            if parsed:
                all_stocks.append(parsed)

        if page == 1:
            print(f"  总量: {total} 只")

        if page % 5 == 0 or len(items) < PAGE_SIZE:
            print(f"  第{page}页: 累计 {len(all_stocks)}/{total}")

        if len(items) < PAGE_SIZE:
            break

        time.sleep(0.3)

    if all_stocks:
        return all_stocks
    return None


# ============================================================
# 数据源 2: akshare
# ============================================================

def fetch_stocks_akshare() -> list[dict]:
    try:
        import akshare as ak
    except ImportError:
        print("akshare 未安装", file=sys.stderr)
        return []

    print("数据源 2: akshare")

    try:
        df = ak.stock_zh_a_spot_em()
    except Exception as e:
        print(f"akshare 获取失败: {e}", file=sys.stderr)
        return []

    if df is None or df.empty:
        return []

    stocks = []
    for _, row in df.iterrows():
        code = str(row.get("代码", "")).strip()
        name = str(row.get("名称", "")).strip()
        if not code or not name or not code.isdigit() or len(code) != 6:
            continue

        industry = str(row.get("所属行业", row.get("行业", "-"))).strip() or "-"
        wuxing = map_industry_to_wuxing(industry)

        stocks.append({
            "code": code,
            "name": name,
            "listDate": "",
            "industry": industry,
            "wuxing": wuxing,
        })

    return stocks


# ============================================================
# 数据源 3: baostock（免费无需注册）
# ============================================================

def fetch_stocks_baostock() -> list[dict]:
    try:
        import baostock as bs
        import pandas as pd
    except ImportError:
        print("baostock / pandas 未安装", file=sys.stderr)
        return []

    print("数据源 3: baostock")

    lg = bs.login()
    if lg.error_code != "0":
        print(f"baostock 登录失败: {lg.error_msg}", file=sys.stderr)
        return []

    try:
        # 获取全部A股列表（含交易日状态）
        rs = bs.query_all_stock(day=datetime.now().strftime("%Y-%m-%d"))
        if rs.error_code != "0":
            print(f"query_all_stock 失败: {rs.error_msg}", file=sys.stderr)
            return []

        stock_list = []
        while rs.next():
            row = rs.get_row_data()
            stock_list.append(row)

        if not stock_list:
            return []

        df_stocks = pd.DataFrame(stock_list, columns=rs.fields)

        stocks = []
        # 过滤A股（sh.60xxxx, sz.00xxxx, sz.30xxxx, sh.68xxxx）
        for _, row in df_stocks.iterrows():
            code_full = str(row.get("code", ""))
            name = str(row.get("code_name", ""))
            if not code_full or not name:
                continue

            # baostock 格式: sh.600001, sz.000001
            if "." in code_full:
                code = code_full.split(".")[-1]
            else:
                code = code_full

            if not code.isdigit() or len(code) != 6:
                continue

            stocks.append({
                "code": code,
                "name": name,
                "listDate": "",
                "industry": "-",
                "wuxing": "water",
            })

        if stocks:
            # 尝试获取行业分类（申万一级）
            try:
                print("  正在获取行业分类...")
                rs_ind = bs.query_stock_industry()
                if rs_ind.error_code == "0":
                    code_industry: dict[str, str] = {}
                    while rs_ind.next():
                        row_ind = rs_ind.get_row_data()
                        code_ind = str(row_ind[0]).split(".")[-1] if "." in str(row_ind[0]) else str(row_ind[0])
                        industry_name = str(row_ind[3]) if len(row_ind) > 3 else ""
                        if code_ind and industry_name:
                            code_industry[code_ind] = industry_name

                    for s in stocks:
                        ind = code_industry.get(s["code"], "")
                        if ind:
                            s["industry"] = ind
                            s["wuxing"] = map_industry_to_wuxing(ind)
            except Exception as e:
                print(f"  获取行业分类失败: {e}", file=sys.stderr)

        return stocks

    finally:
        bs.logout()


# ============================================================
# 合并逻辑
# ============================================================

def fetch_stocks() -> list[dict]:
    """
    三级降级获取新股票:
      1) 东方财富 API（代码+名称+行业+上市日期，最全）
      2) akshare（代码+名称）
      3) baostock（代码+名称+申万一级行业）
    """
    stocks = fetch_stocks_eastmoney()
    if stocks:
        return stocks

    print("\n东方财富 API 不可用，尝试备用方案 1...", file=sys.stderr)
    stocks = fetch_stocks_akshare()
    if stocks:
        return stocks

    print("\nakshare 不可用，尝试备用方案 2...", file=sys.stderr)
    stocks = fetch_stocks_baostock()
    if stocks:
        return stocks

    print("\n所有数据源均不可用", file=sys.stderr)
    sys.exit(1)


def merge_stocks(existing: dict[str, dict], new_stocks: list[dict]) -> list[dict]:
    """
    去重合并：已有股票保留不动，新股票按 code 去重后追加。
    返回合并后的股票列表（保持顺序：先已有，再新增）。
    """
    merged = list(existing.values())
    existing_codes = set(existing.keys())
    added = 0

    for s in new_stocks:
        if s["code"] not in existing_codes:
            merged.append(s)
            existing_codes.add(s["code"])
            added += 1

    print(f"  已有: {len(existing)} 只, 新增: {added} 只, 合并后: {len(merged)} 只")
    return merged


# ============================================================
# 写入文件
# ============================================================

def generate_batch_files(stocks: list[dict], output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)

    # 清理旧的批次文件
    for old in sorted(output_dir.glob("stocks_batch*.ts")):
        old.unlink()
        print(f"  清理旧文件: {old.name}")

    total = len(stocks)
    batch_count = (total + BATCH_SIZE - 1) // BATCH_SIZE

    stocks_ts = output_dir / "stocks.ts"
    if stocks_ts.exists():
        content = stocks_ts.read_text(encoding="utf-8")
        content = re.sub(r"export const TOTAL_STOCK_COUNT = \d+;",
                         f"export const TOTAL_STOCK_COUNT = {total};", content)
        content = re.sub(r"const BATCH_COUNT = \d+;",
                         f"const BATCH_COUNT = {batch_count};", content)
        stocks_ts.write_text(content, encoding="utf-8")
        print(f"已更新 stocks.ts: TOTAL_STOCK_COUNT={total}, BATCH_COUNT={batch_count}")

    ts_now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    for batch_idx in range(batch_count):
        start = batch_idx * BATCH_SIZE
        end = min(start + BATCH_SIZE, total)
        batch_stocks = stocks[start:end]

        lines = [
            f"// 股票数据批次 {batch_idx} - 共{len(batch_stocks)}只",
            f"// 自动生成于 {ts_now}",
            "// 数据来源: 东方财富公开API / akshare / baostock",
            "import type { StockData } from './stocks';",
            "",
            f"export const BATCH_{batch_idx}: StockData[] = [",
        ]

        for s in batch_stocks:
            name_esc = s["name"].replace("\\", "\\\\").replace("'", "\\'")
            ind_esc = s["industry"].replace("\\", "\\\\").replace("'", "\\'")
            lines.append(
                f"  {{ code: '{s['code']}', name: '{name_esc}', "
                f"listDate: '{s['listDate']}', sector: '{ind_esc}', "
                f"wuxing: '{s['wuxing']}' }},"
            )

        lines.append("];\n")

        filepath = output_dir / f"stocks_batch{batch_idx}.ts"
        filepath.write_text("\n".join(lines), encoding="utf-8")
        print(f"  已写入 {filepath.name}: {len(batch_stocks)} 只股票")


# ============================================================
# 统计 & 入口
# ============================================================

def print_stats(stocks: list[dict]):
    counts = {}
    for s in stocks:
        w = s["wuxing"]
        counts[w] = counts.get(w, 0) + 1

    print(f"\n===== 统计 =====")
    print(f"总股票数: {len(stocks)}")
    names = {"metal": "金", "wood": "木", "water": "水", "fire": "火", "earth": "土"}
    for w in ["metal", "wood", "water", "fire", "earth"]:
        c = counts.get(w, 0)
        pct = c / len(stocks) * 100 if stocks else 0
        print(f"  {names[w]}({w}): {c} 只 ({pct:.1f}%)")
    has_date = sum(1 for s in stocks if s["listDate"])
    has_ind = sum(1 for s in stocks if s["industry"] and s["industry"] != "-")
    print(f"有上市日期: {has_date}")
    print(f"有行业分类: {has_ind}")


def main():
    project_root = Path(__file__).resolve().parent.parent
    output_dir = project_root / OUTPUT_DIR

    print("=" * 60)
    print("  玄股 - A股股票池更新（去重合并模式）")
    print(f"  运行时间: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("=" * 60)

    # 1. 读取已有股票
    print("\n[1/3] 读取已有股票数据...")
    existing = read_existing_stocks(output_dir)

    # 2. 获取新股票
    print("\n[2/3] 获取最新A股列表...")
    new_stocks = fetch_stocks()

    # 3. 去重合并
    print("\n[3/3] 去重合并...")
    merged = merge_stocks(existing, new_stocks)

    if not merged:
        print("合并结果为空", file=sys.stderr)
        sys.exit(1)

    print_stats(merged)
    print(f"\n正在写入 TypeScript 数据文件...")
    generate_batch_files(merged, output_dir)

    added = len(merged) - len(existing)
    print(f"\n✅ 完成！原有 {len(existing)} 只 + 新增 {added} 只 = 共 {len(merged)} 只")


if __name__ == "__main__":
    main()