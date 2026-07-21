import requests
import json
import hashlib
import re
import time
import os
from datetime import datetime, timezone, timedelta
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO

# ─────────────────────────────────────────────────────────────────────────────
# TIMEZONE & HELPERS
# ─────────────────────────────────────────────────────────────────────────────

VN_TZ = timezone(timedelta(hours=7))


def now_vn() -> datetime:
    return datetime.now(tz=VN_TZ)


def parse_kickoff(time_str: str):
    """Parse '2026-07-21 18:00:00+07' → datetime aware (VN tz)."""
    if not time_str:
        return None
    try:
        # Python <3.11 không parse +07 (thiếu phút), cần补 :00
        s = time_str.strip()
        tz_part = re.search(r'([+-])(\d{2})(?::(\d{2}))?$', s)
        if tz_part:
            sign, hh, mm = tz_part.group(1), tz_part.group(2), tz_part.group(3)
            fixed_tz = f"{sign}{hh}:{mm or '00'}"
            s = s[:tz_part.start()] + fixed_tz
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=VN_TZ)
        return dt
    except Exception:
        return None


def format_match_time(time_str: str) -> str:
    """'2026-07-21 18:00:00+07' → '18:00 21/07'"""
    dt = parse_kickoff(time_str)
    if dt:
        return dt.strftime("%H:%M %d/%m")
    return time_str


def parse_time_sort(time_str: str) -> int:
    dt = parse_kickoff(time_str)
    if dt:
        return dt.hour * 100 + dt.minute
    return 9999


# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://choangtv18.com/",
}

API_URL    = "https://api.choangtv18.com/matchSchedule/getList"
CDN_BASE   = "https://cdn.sports-cas889abxfileposo.site/live"
SITE_URL   = "https://choangtv18.com"
THUMBS_DIR = "thumbs"
REPO_RAW   = os.environ.get("REPO_RAW", "")

THUMB_VERSION = "v1"


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def make_id(text, prefix):
    h = hashlib.md5(text.encode()).hexdigest()[:10]
    return f"{prefix}-{h}"


def fetch_image(url):
    try:
        res = requests.get(url, headers=HEADERS, timeout=8)
        return Image.open(BytesIO(res.content)).convert("RGBA")
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# THUMBNAIL
# ─────────────────────────────────────────────────────────────────────────────

def make_thumbnail(match, channel_id):
    os.makedirs(THUMBS_DIR, exist_ok=True)
    cache_key = match.get("logo_a", "") + match.get("logo_b", "") + THUMB_VERSION
    logo_hash = hashlib.md5(cache_key.encode()).hexdigest()[:8]
    date_str  = now_vn().strftime("%Y%m%d")
    out_path  = f"{THUMBS_DIR}/{channel_id}_{logo_hash}_{date_str}.png"

    if os.path.exists(out_path):
        return out_path

    W, H = 1600, 1200
    HEADER_H = 180
    FOOTER_H = 160

    bg   = Image.new("RGB", (W, H), (245, 245, 248))
    draw = ImageDraw.Draw(bg)

    for y in range(HEADER_H, H - FOOTER_H):
        ratio = (y - HEADER_H) / (H - FOOTER_H - HEADER_H)
        gray  = int(248 - ratio * 18)
        draw.line([(0, y), (W, y)], fill=(gray, gray, gray + 4))

    draw.rectangle([(0, 0),            (W, HEADER_H)],  fill=(13, 20, 40))
    draw.rectangle([(0, H - FOOTER_H), (W, H)],         fill=(13, 20, 40))

    ACCENT = (220, 30, 40)
    draw.rectangle([(0, HEADER_H),         (W, HEADER_H + 5)], fill=ACCENT)
    draw.rectangle([(0, H - FOOTER_H - 5), (W, H - FOOTER_H)], fill=ACCENT)

    FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    try:
        font_vs   = ImageFont.truetype(FONT_BOLD, 160)
        font_time = ImageFont.truetype(FONT_BOLD, 100)
        font_team = ImageFont.truetype(FONT_BOLD, 58)
    except Exception:
        font_vs = font_time = font_team = ImageFont.load_default()

    content_top = HEADER_H + 5
    content_bot = H - FOOTER_H - 5
    content_h   = content_bot - content_top

    logo_size     = 360
    name_h        = 120
    time_h        = 110
    gap_logo_name = 40
    gap_name_time = 60

    total_block_h = logo_size + gap_logo_name + name_h + gap_name_time + time_h
    block_top     = content_top + (content_h - total_block_h) // 2

    logo_y       = block_top
    name_block_y = logo_y + logo_size + gap_logo_name
    name_center  = name_block_y + name_h // 2
    time_y       = name_block_y + name_h + gap_name_time + time_h // 2

    # Logo trái
    if match.get("logo_a"):
        img = fetch_image(match["logo_a"])
        if img:
            img = img.resize((logo_size, logo_size), Image.LANCZOS)
            bg.paste(img, (W // 4 - logo_size // 2, logo_y), img)

    # Logo phải
    if match.get("logo_b"):
        img = fetch_image(match["logo_b"])
        if img:
            img = img.resize((logo_size, logo_size), Image.LANCZOS)
            bg.paste(img, (W * 3 // 4 - logo_size // 2, logo_y), img)

    # VS
    draw.text((W // 2, logo_y + logo_size // 2), "VS",
              fill=ACCENT, font=font_vs, anchor="mm")

    # Tên đội — tự thu nhỏ nếu quá dài
    def draw_team_name(text, cx):
        max_width = W // 2 - 60
        font_size = 58
        f = font_team
        while font_size >= 28:
            try:
                f = ImageFont.truetype(FONT_BOLD, font_size)
            except Exception:
                f = ImageFont.load_default()
            bbox = draw.textbbox((0, 0), text, font=f)
            if (bbox[2] - bbox[0]) <= max_width:
                break
            font_size -= 3
        draw.text((cx, name_center), text, fill=(20, 20, 20), font=f, anchor="mm")

    if match.get("team_a"):
        draw_team_name(match["team_a"], W // 4)
    if match.get("team_b"):
        draw_team_name(match["team_b"], W * 3 // 4)

    # Giờ đấu
    if match.get("time_display"):
        draw.text((W // 2 + 4, time_y + 4), match["time_display"],
                  fill=ACCENT, font=font_time, anchor="mm")
        draw.text((W // 2, time_y), match["time_display"],
                  fill=(15, 15, 15), font=font_time, anchor="mm")

    # Tên giải — header
    if match.get("league"):
        league_text = match["league"].upper()
        font_size   = 62
        f           = None
        while font_size >= 28:
            try:
                f = ImageFont.truetype(FONT_BOLD, font_size)
            except Exception:
                f = ImageFont.load_default()
            bbox = draw.textbbox((0, 0), league_text, font=f)
            if (bbox[2] - bbox[0]) <= W - 60:
                break
            font_size -= 3
        draw.text((W // 2, HEADER_H // 2), league_text,
                  fill=(255, 255, 255), font=f, anchor="mm")

    # Viền ngoài
    draw.rectangle([(0, 0), (W - 1, H - 1)], outline=(180, 180, 180), width=3)
    bg.save(out_path, "PNG", optimize=True)
    return out_path


def cleanup_old_thumbs(days: int = 3):
    if not os.path.exists(THUMBS_DIR):
        return
    cutoff  = now_vn() - timedelta(days=days)
    removed = 0
    for fname in os.listdir(THUMBS_DIR):
        if not fname.endswith(".png"):
            continue
        m = re.search(r'_(\d{8})\.png$', fname)
        if not m:
            try:
                os.remove(os.path.join(THUMBS_DIR, fname))
                removed += 1
            except Exception:
                pass
            continue
        try:
            file_date = datetime.strptime(m.group(1), "%Y%m%d").replace(tzinfo=VN_TZ)
        except ValueError:
            continue
        if file_date < cutoff:
            try:
                os.remove(os.path.join(THUMBS_DIR, fname))
                removed += 1
            except Exception:
                pass
    if removed:
        print(f"Da xoa {removed} thumbnail cu (>{days} ngay)")


# ─────────────────────────────────────────────────────────────────────────────
# SCRAPE MATCHES — API JSON (không BeautifulSoup)
# ─────────────────────────────────────────────────────────────────────────────

def get_matches():
    today = now_vn()
    # Lấy today + tomorrow để覆盖 qua nửa đêm
    dates_to_fetch = [today]
    if today.hour >= 18:
        dates_to_fetch.append(today + timedelta(days=1))

    all_matches = []
    seen_ids    = set()

    for date in dates_to_fetch:
        date_str = date.strftime("%Y-%m-%d")
        try:
            res = requests.get(API_URL, params={"date": date_str},
                               headers=HEADERS, timeout=15)
            data = res.json()
        except Exception as e:
            print(f"  Loi API date={date_str}: {e}")
            continue

        if data.get("code") != 200:
            continue

        for item in data.get("data", []):
            match_id = str(item.get("id", ""))
            if not match_id or match_id in seen_ids:
                continue
            seen_ids.add(match_id)

            # Bỏ trận đã kết thúc
            if item.get("end", False):
                continue

            time_raw     = item.get("time", "")
            time_display = format_match_time(time_raw)
            team_a       = item.get("name1", "").strip()
            team_b       = item.get("name2", "").strip()
            logo_a       = item.get("logo1", "")
            logo_b       = item.get("logo2", "")
            league       = item.get("league", "").strip()
            caster_raw   = item.get("caster", "").strip()
            score1       = item.get("score1", 0) or 0
            score2       = item.get("score2", 0) or 0
            is_live      = item.get("live", False)

            # Tên hiển thị: live có tỷ số thì hiện, chưa live thì vs
            if is_live and (score1 > 0 or score2 > 0):
                name = f"{team_a} {score1}-{score2} {team_b}"
            else:
                name = f"{team_a} vs {team_b}"

            if not name.replace("vs", "").replace("-", "").strip():
                name = f"Tran {match_id}"

            # "BLV Lee Min Hoo" → "Lee Min Hoo"
            caster_clean = re.sub(r'^BLV\s*', '', caster_raw).strip()

            all_matches.append({
                "match_id":     match_id,
                "name":         name,
                "time":         time_display,
                "time_display": time_display,
                "time_raw":     time_raw,
                "time_sort":    parse_time_sort(time_raw),
                "team_a":       team_a,
                "team_b":       team_b,
                "logo_a":       logo_a,
                "logo_b":       logo_b,
                "league":       league,
                "caster":       caster_clean,
                "score1":       score1,
                "score2":       score2,
                "is_live":      is_live,
                "hot":          item.get("hot", False),
                "subtitle":     item.get("subtitle", ""),
                "category":     item.get("category", "BIDA"),
                # Stream URL construct trực tiếp từ match_id
                "stream_url":   f"{CDN_BASE}/live{match_id}/index.m3u8",
            })

    # LIVE lên đầu → rồi sort theo giờ tăng dần
    all_matches.sort(key=lambda m: (0 if m["is_live"] else 1, m["time_sort"]))
    return all_matches


# ─────────────────────────────────────────────────────────────────────────────
# BUILD CHANNEL JSON
# ─────────────────────────────────────────────────────────────────────────────

def build_channel(match, thumb_url=""):
    uid    = make_id(match["stream_url"], "chtv")
    src_id = make_id(match["stream_url"], "src")
    ct_id  = make_id(match["stream_url"], "ct")
    st_id  = make_id(match["stream_url"], "st")
    lnk_id = make_id(match["stream_url"], "lnk")

    label_text  = "● LIVE" if match["is_live"] else "🕐 Sắp"
    label_color = "#ff4444" if match["is_live"] else "#aaaaaa"

    # Tên channel: tên trận | giờ (chưa live) | BLV
    display_name = match["name"]
    if match["time"] and not match["is_live"]:
        display_name = f"{match['name']} | {match['time']}"
    if match["caster"]:
        display_name += f" | {match['caster']}"

    stream_links = [{
        "id":      lnk_id,
        "name":    match["caster"] if match["caster"] else "Link HD",
        "type":    "hls",
        "default": True,
        "url":     match["stream_url"],
        "request_headers": [
            {"key": "Referer",    "value": "https://choangtv18.com/"},
            {"key": "User-Agent", "value": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        ],
    }]

    channel = {
        "id":            uid,
        "name":          display_name,
        "type":          "single",
        "display":       "thumbnail-only",
        "enable_detail": False,
        "labels": [{"text": label_text, "position": "top-left",
                    "color": "#00000080", "text_color": label_color}],
        "sources": [{
            "id":   src_id,
            "name": "ChoangTV",
            "contents": [{
                "id":   ct_id,
                "name": match["name"],
                "streams": [{"id": st_id, "name": "CHTV", "stream_links": stream_links}],
            }],
        }],
        "org_metadata": {
            "league":  match.get("league", ""),
            "team_a":  match.get("team_a", ""),
            "team_b":  match.get("team_b", ""),
            "logo_a":  match.get("logo_a", ""),
            "logo_b":  match.get("logo_b", ""),
            "time":    match.get("time", ""),
            "caster":  match.get("caster", ""),
            "score":   f"{match.get('score1', 0)}-{match.get('score2', 0)}",
            "is_live": match["is_live"],
            "hot":     match.get("hot", False),
        },
    }

    if thumb_url:
        channel["image"] = {
            "padding":          1,
            "background_color": "#ffffff",
            "display":          "contain",
            "url":              thumb_url,
            "width":            1600,
            "height":           1200,
        }

    return channel


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    os.makedirs(THUMBS_DIR, exist_ok=True)
    cleanup_old_thumbs(days=3)
    print(f"Gio VN h
