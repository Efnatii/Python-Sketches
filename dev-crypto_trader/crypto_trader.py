# -*- coding: utf-8 -*-
import pygame, requests, threading, time, os, json, numpy as np, pandas as pd, warnings
from math import floor
import shutil

# ------------------------- Darts -------------------------
try:
    from darts import TimeSeries
    from darts.models import NBEATSModel
    DARTS_AVAILABLE, DARTS_ERR = True, None
except Exception as e:
    DARTS_AVAILABLE, DARTS_ERR = False, e

TRADES_DIR = "trades"
MAX_TRADES_KEEP = 500  # сколько сделок храним на пару
os.makedirs(TRADES_DIR, exist_ok=True)


# ------------------------- UI/Размеры --------------------
WIDTH, HEIGHT, FPS = 1180, 680, 60
RIGHT_PANEL_W = 300
COLOR_BG = (19, 20, 26)
COLOR_TEXT = (245, 245, 245)
COLOR_HINT = (165, 165, 175)
PLOT_RECT   = pygame.Rect(10, 50, WIDTH - RIGHT_PANEL_W - 20, HEIGHT - 60)
STATUS_RECT = pygame.Rect(WIDTH - RIGHT_PANEL_W + 6, 50, RIGHT_PANEL_W - 12, 170)
TRADES_RECT = pygame.Rect(WIDTH - RIGHT_PANEL_W + 6, STATUS_RECT.bottom + 6,
                          RIGHT_PANEL_W - 12, HEIGHT - (STATUS_RECT.bottom + 16))
SEARCH_RECT = pygame.Rect(10, 10, 320, 26)
PERIOD_RECT = pygame.Rect(340, 10, 120, 26)
AI_RECT     = pygame.Rect(WIDTH - 110, 10, 70, 22)  # чекбокс «ИИ»
HELP_RECT   = pygame.Rect(WIDTH - 35, 10, 25, 25)
TOPBAR_Y    = 10


# ------------------------- Биржевые профили комиссий ----
EXCH_PROFILES = {
    "binance_futures": {"fee_open": 0.0004, "fee_close": 0.0004, "name": "Binance Futures"},
    "bybit_perp":      {"fee_open": 0.00055,"fee_close": 0.00055,"name": "Bybit USDT Perp"},
    "spot":            {"fee_open": 0.0010, "fee_close": 0.0010, "name": "Spot 0.1%"},
}
DEFAULT_EXCH = "binance_futures"

# ------------------------- Источники цен -----------------
BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"
BINANCE_PRICE_URL  = "https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
BINANCE_ALL_TICKERS_URL = "https://api.binance.com/api/v3/ticker/price"

CACHE_DIR, MODEL_DIR = "cache", "ai_models"
os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(MODEL_DIR, exist_ok=True)

# порог для пометки реального «лишнего» разрыва (см. CandlesChart.draw)
GAP_THRESHOLD_SEC = 80

# ------------------------- AI базовые --------------------
AI_INPUT_LEN = 120
AI_PRED_HORIZON = 5
AI_MIN_CANDLES = 180
AI_MAX_TRAIN_CANDLES = 2000
AI_MIN_MOVE = 0.0007
AI_NEXT_DEFAULT = 45
AI_SL_PCT = 0.003                     # базовый нижний порог (0.3%) — используется как фоллбек
AI_HOLD_MIN_SEC, AI_HOLD_MAX_SEC = 5*60, 15*60

# stake и управление риском
AI_STAKE_FRAC = 0.05                  # было 0.15 — снизили риск на сделку
AI_R_MULT      = 1.6                  # целевая доходность ≈ 1.6R
AI_ATR_N_TRAIN = 60                   # окно ATR для стопа/таргета
AI_SIGMA_N     = 180                  # окно σ лог-доходностей
AI_COOLDOWN_SEC = 600                 # пауза после убыточной сделки

# Ограничители TP/SL
AI_TARGET_MIN_PCT, AI_TARGET_MAX_PCT = 0.001, 0.004

AI_REFIT_MIN_NEW = 15   # минимум новых точек, чтобы запускать дообучение (15 минут)

# Фантомы (отрисовка прогноза)
PHANTOM_ATR_N = 60
PHANTOM_ATR_K = 0.5
RET_STD_N = 120            # окно σ доходностей для «успокоения» прогноза
RET_CAP_MIN = 0.0015       # минимум «кепа» изменения за шаг (0.15%)
RET_CAP_MULT = 2.0         # ограничиваем |r_step| <= max(RET_CAP_MIN, RET_CAP_MULT*σ)

AI_MIN_EDGE_BPS = 5        # было 8 → 0.05% превеса над шумом+комиссией
AI_SLOPE_Z_MIN  = 0.4      # было 0.6
AI_TREND_ABS_MIN = 0.00015 # ~1.5 б.п. для MA20–MA60
AI_STRONG_EDGE_K = 1.10    # «сильный» сигнал: edge ≥ 1.10 * min_edge → пускаем без тренд-фильтра

FORCE_HISTORY_SECONDS = 7*24*3600   # всегда тянем ровно 7 дней, если кэша нет
GAP_STRICT_SEC        = 60          # любой разрыв > 1 мин заполняем
TAIL_RELOAD_MIN       = 120         # сколько минут хвоста перезагружать точными свечами

AI_REFIT_EPOCHS = 3          # сколько эпох делать при дообучении
AI_REFIT_LR     = 1e-4       # малый шаг обучения при дообучении
AI_REFIT_DRIFT_K = 3.0       # допустимое среднее расхождение прогноза после refit = max(RET_CAP_MIN, K*sigma)

RISK_PER_TRADE = 0.02   # 2% баланса рискуем на сделку
STAKE_MIN      = 5.0    # минимум денег в позицию
STAKE_MAX_FRAC = 0.5    # потолок: не больше 50% баланса в позицию

# Для калибровки прогноза
CALIB_EMA_ALPHA   = 0.35   # сглаживание шагов прогноза (0..1)
CALIB_SHRINK_LONG = 0.6    # чем дальше по горизонту, тем сильнее «успокаиваем»

# Для фантомов (квантильный «коридор» волатильности)
PHANTOM_Q_LOW   = 0.15     # нижний квантиль минутных лог-доходностей
PHANTOM_Q_HIGH  = 0.85     # верхний квантиль
PHANTOM_WICK_CAP_ATR = 2.5 # жесткий потолок фитилей = 2.5*ATR
PHANTOM_SLOPE_BOOST  = 2.5 # усиление фитилей при резком шаге

PHANTOM_STRICT = True  # строгие фантомы: тело точно по прогнозу, без ATR-фитилей


AI_ALWAYS_REFIT = True  # поставь False — и refit будет только если появились новые свечи

warnings.filterwarnings("ignore", message="'T' is deprecated", module="darts")

# ------------------------- Вспомогательные ----------------
def cache_path(symbol): return os.path.join(CACHE_DIR, f"{symbol.upper()}.json")
def model_path(symbol): return os.path.join(MODEL_DIR, f"{symbol.upper()}.nbeats.pth")
def meta_path(symbol): return os.path.join(MODEL_DIR, f"{symbol.upper()}.meta.json")


def dedupe_candles(candles):
    by_ts = {}
    for ts,o,h,l,c,is_pre in candles:
        by_ts[float(ts)] = (float(ts), float(o), float(h), float(l), float(c), bool(is_pre))
    return [by_ts[t] for t in sorted(by_ts.keys())]

def load_cache(symbol):
    p = cache_path(symbol)
    if not os.path.exists(p): return {"candles": [], "saved_at": 0.0}, False
    try:
        obj = json.load(open(p, "r", encoding="utf-8"))
        raw = obj.get("candles", [])
        res = []
        for c in raw:
            ts,o,h,l,cl,is_pre = c if len(c)==6 else (c[0],c[1],c[2],c[3],c[4],True)
            res.append((float(ts),float(o),float(h),float(l),float(cl),bool(is_pre)))
        return {"candles": dedupe_candles(res), "saved_at": float(obj.get("saved_at",0.0))}, True
    except Exception as e:
        print("Ошибка кэша:", e); return {"candles": [], "saved_at": 0.0}, False

def save_cache(symbol, candles, saved_at=None):
    if saved_at is None: saved_at = time.time()
    ser = [[c[0],c[1],c[2],c[3],c[4],c[5]] for c in dedupe_candles(candles)]
    json.dump({"candles": ser, "saved_at": saved_at}, open(cache_path(symbol),"w",encoding="utf-8"))

def fetch_candles_binance(symbol, seconds):
    minutes, all_klines, end_time = max(1, seconds//60+1), [], None
    while minutes>0:
        limit = min(1000, minutes)
        params={"symbol":symbol,"interval":"1m","limit":limit}
        if end_time is not None: params["endTime"] = end_time-1
        part = requests.get(BINANCE_KLINES_URL, params=params, timeout=6).json()
        if not isinstance(part,list) or not part: break
        all_klines = part + all_klines
        end_time = part[0][0]; minutes -= len(part)
    res=[]
    for k in all_klines:
        ts = k[0]/1000.0; o,h,l,c = map(float, (k[1],k[2],k[3],k[4]))
        res.append((ts,o,h,l,c,True))
    return dedupe_candles(res)

def fetch_range_binance(symbol, t0, t1):
    res=[]; cur=int(t0*1000); end=int(t1*1000)
    while cur<end:
        params={"symbol":symbol,"interval":"1m","startTime":cur,"endTime":end,"limit":1000}
        part = requests.get(BINANCE_KLINES_URL, params=params, timeout=6).json()
        if not isinstance(part,list) or not part: break
        for k in part:
            ts=k[0]/1000.0; o,h,l,c=map(float,(k[1],k[2],k[3],k[4]))
            res.append((ts,o,h,l,c,True))
        last = part[-1][0]
        if last==cur: break
        cur = last + 60_000
    return dedupe_candles(res)

# сколько минут «хвоста» перезагружаем заново (он мог быть онлайн/неполный)
TAIL_REFRESH_MIN = 15
ONE_MINUTE = 60
CONFLICT_MAX_REPEATS = 3          # после 3 подряд конфликтов — входим малой позицией
CONFLICT_SMALL_STAKE  = 0.35      # доля обычной ставки для «форс-входа»
CONFLICT_RECHECK_OFFSET_SEC = 2.0 # смещение после закрытия бара

def _fill_gaps_and_refresh(symbol: str, candles: list, refresh_tail_min: int) -> list:
    """
    1) Вшивает недостающие минуты между свечами (любой разрыв > 60 с).
    2) Перезагружает «хвост» последних refresh_tail_min минут заново с биржи.
    """
    if not candles:
        return candles

    candles = dedupe_candles(candles)
    fixed = list(candles)

    # 1) прошиваем ВСЕ разрывы > 60 с (не по порогу 80, а любые)
    i = 0
    while i < len(fixed) - 1:
        a = fixed[i]
        b = fixed[i + 1]
        if (b[0] - a[0]) > ONE_MINUTE:
            # берём строго «между» минутами, чтобы не дублировать соседей
            fill = fetch_range_binance(symbol, a[0] + ONE_MINUTE, b[0] - ONE_MINUTE)
            if fill:
                fixed[i + 1:i + 1] = fill
                i += len(fill)
                continue
        i += 1

    # 2) полностью перезагружаем хвост последних N минут (мог быть онлайн)
    last_ts = fixed[-1][0]
    tail_from = max(fixed[0][0], last_ts - refresh_tail_min * ONE_MINUTE)
    fresh = fetch_range_binance(symbol, tail_from, time.time())

    if fresh:
        cut_ts = fresh[0][0]
        head = [c for c in fixed if c[0] < cut_ts]
        fixed = dedupe_candles(head + fresh)

    return fixed

def ensure_history(symbol: str, seconds: int, shared_state: dict, only_fill_gaps: bool = False):
    """
    Гарантирует историю для пары:
      - если кэша нет → скачиваем 'seconds' назад (для нас — всегда 7 дней);
      - если кэш есть → прошиваем любые разрывы и перезагружаем хвост последних TAIL_REFRESH_MIN минут;
      - записываем обратно в кэш и кладём в shared_state["data"].
    ПОД СИГНАТУРУ: (symbol, seconds, shared_state, only_fill_gaps=False)
    """
    now = time.time()
    obj, ok = load_cache(symbol)
    candles = obj.get("candles", [])

    # нет кэша — тянем целиком "seconds" (7 дней)
    if (not ok) or (not candles):
        back = fetch_candles_binance(symbol, seconds)
        candles = dedupe_candles(back)
        save_cache(symbol, candles, saved_at=now)
    else:
        # прошиваем разрывы + перезагрузка хвоста
        candles = _fill_gaps_and_refresh(symbol, candles, TAIL_REFRESH_MIN)

        # при полном режиме (only_fill_gaps=False) проверим, что начало покрывает нужный период
        if not only_fill_gaps:
            need_from = now - seconds
            if candles and candles[0][0] > need_from + ONE_MINUTE:
                # не хватает начального отрезка — дотянем недостающее
                need_sec = int(candles[0][0] - need_from)
                more = fetch_candles_binance(symbol, need_sec)
                if more:
                    candles = dedupe_candles(more + candles)

        save_cache(symbol, candles, saved_at=now)

    # положим в shared_state
    with shared_state["lock"]:
        shared_state["data"] = candles
        shared_state["base_time"] = candles[0][0] if candles else now

# ------------------------- Darts модель -------------------

class DartsPriceModel:
    """
    Безопасное обучение/дообучение:
    - первичное обучение (n_epochs=10);
    - перед каждой сделкой: лёгкий refit (epochs=AI_REFIT_EPOCHS, lr=AI_REFIT_LR);
    - "safety net": если прогноз после refit слишком отклоняется от прежнего
      относительно локальной волатильности — откатываемся на .bak и используем старый прогноз.

    Возвращает: (forecast_TimeSeries, info_dict)
      info_dict:
        had_pretrained: bool
        loaded_span: (start_ts, end_ts) | None
        init_trained: bool
        train_span: (start_ts, end_ts) | None
        refit_done: bool
        refit_span: (start_ts, end_ts) | None
        refit_reverted: bool
    """
    def __init__(self, symbol):
        self.symbol = symbol
        self.path   = model_path(symbol)
        self.model  = None
        self.trained = False
        self.meta = self._load_meta()

    # ---------- утилиты ----------
    def _load_meta(self):
        p = meta_path(self.symbol)
        try: return json.load(open(p, "r", encoding="utf-8"))
        except Exception: return {}

    def _save_meta(self, **kv):
        self.meta.update(kv)
        json.dump(self.meta, open(meta_path(self.symbol), "w", encoding="utf-8"))

    def _series(self, candles):
        times = pd.to_datetime([c[0] for c in candles], unit="s", utc=True).tz_convert(None)
        vals  = np.asarray([c[4] for c in candles], dtype=np.float32)
        s = pd.Series(vals, index=pd.DatetimeIndex(times))
        s = s[~s.index.duplicated(keep="last")].sort_index().asfreq("T", method="ffill")
        return TimeSeries.from_series(s)

    def _sigma_from(self, candles, n=RET_STD_N):
        closes = [c[4] for c in candles[-n:]] or [candles[-1][4]]
        rets = np.diff(np.log(np.maximum(1e-12, np.array(closes, dtype=np.float64))))
        return float(np.std(rets)) if len(rets) >= 3 else 0.0

    def load_or_create(self, in_len, out_len):
        """
        Не грузим с диска, если модель уже есть в памяти (self.model is not None).
        """
        if self.model is not None:
            return

        if os.path.exists(self.path):
            try:
                self.model = NBEATSModel.load(self.path)
                self.trained = True
                return
            except Exception:
                pass

        # новая модель (учти: если ты используешь «безопасную» версию класса,
        # оставь optimizer_kwargs, как в твоём текущем конструкторе)
        self.model = NBEATSModel(
            input_chunk_length=in_len,
            output_chunk_length=out_len,
            n_epochs=10,
            random_state=42,
            force_reset=True,
            optimizer_kwargs={"lr": AI_REFIT_LR}  # если у тебя есть эта константа
        )
        self.trained = False

    # ---------- основной метод ----------
    def fit_predict(self, candles, in_len=AI_INPUT_LEN, out_len=AI_PRED_HORIZON, always_refit=AI_ALWAYS_REFIT):
        ts = self._series(candles)
        self.load_or_create(in_len, out_len)

        train_start_ts = float(candles[0][0])
        train_end_ts = float(candles[-1][0])
        prev_start = float(self.meta.get("train_start_ts", train_start_ts))
        prev_end = float(self.meta.get("trained_until", 0.0))
        had_pretrained = bool(self.trained and self.meta and self.meta.get("trained_n", 0) > 0)

        info = {
            "had_pretrained": had_pretrained,
            "loaded_span": (prev_start, prev_end) if had_pretrained and prev_end > 0 else None,
            "init_trained": False,
            "train_span": None,
            "refit_done": False,
            "refit_span": None,
            "refit_reverted": False,
            "skipped_refit": False,
        }

        # первичное обучение
        if not self.trained:
            self.model.fit(ts, verbose=False)
            self.model.save(self.path)
            self.trained = True
            self._save_meta(trained_n=len(ts), train_start_ts=train_start_ts, trained_until=train_end_ts)
            info["init_trained"] = True
            info["train_span"] = (train_start_ts, train_end_ts)

        # прогноз до refit (и возможность его вернуть, если refit не нужен)
        try:
            fc_before = self.model.predict(out_len, series=ts)
            pred_before = np.asarray(fc_before.univariate_values(), dtype=np.float64)
        except Exception:
            fc_before = None
            pred_before = None

        # нет новых данных и refit не обязателен — пропускаем
        if had_pretrained and (train_end_ts <= prev_end) and (not always_refit):
            info["skipped_refit"] = True
            return fc_before, info

        # ---- безопасный refit (как раньше)
        bak_path = None
        if os.path.exists(self.path):
            bak_path = self.path + ".bak"
            try:
                shutil.copyfile(self.path, bak_path)
            except Exception:
                bak_path = None

        try:
            self.model.fit(ts, verbose=False, epochs=AI_REFIT_EPOCHS)
        except TypeError:
            self.model.fit(ts, verbose=False)

        fc_after = self.model.predict(out_len, series=ts)
        pred_after = np.asarray(fc_after.univariate_values(), dtype=np.float64)

        # проверка стабильности
        closes = [c[4] for c in candles[-RET_STD_N:]] or [candles[-1][4]]
        rets = np.diff(np.log(np.maximum(1e-12, np.array(closes))))
        sigma = float(np.std(rets)) if len(rets) >= 3 else 0.0
        drift_cap = max(RET_CAP_MIN, AI_REFIT_DRIFT_K * sigma)
        unstable = False
        if pred_before is not None and pred_before.shape == pred_after.shape:
            start_price = float(candles[-1][4])
            denom = np.maximum(1e-12, np.array([start_price] + pred_before[:-1].tolist()))
            mean_rel = float(np.mean(np.abs(pred_after - pred_before) / denom))
            if mean_rel > drift_cap:
                unstable = True

        if unstable and bak_path and os.path.exists(bak_path):
            try:
                shutil.copyfile(bak_path, self.path)
                self.model = NBEATSModel.load(self.path)
            except Exception:
                pass
            info["refit_reverted"] = True
            fc = fc_before if fc_before is not None else fc_after
            try:
                os.remove(bak_path)
            except Exception:
                pass
        else:
            if train_end_ts > prev_end:
                info["refit_done"] = True
                info["refit_span"] = (prev_end + 60.0, train_end_ts) if prev_end else (train_start_ts, train_end_ts)
            self.model.save(self.path)
            fc = fc_after
            if bak_path and os.path.exists(bak_path):
                try:
                    os.remove(bak_path)
                except Exception:
                    pass

        self._save_meta(trained_n=len(ts), train_start_ts=train_start_ts, trained_until=train_end_ts)
        return fc, info


# ------------------------- Калибровка прогноза ------------
def calibrate_forecast(last_price, pred_values, candles):
    """
    Сглаженный, «успокоенный» прогноз.
    """
    if not pred_values:
        return []

    closes = [c[4] for c in candles[-RET_STD_N:]] or [last_price]
    rets   = np.diff(np.log(np.maximum(1e-12, np.asarray(closes, dtype=np.float64))))
    sigma  = float(np.std(rets)) if len(rets) >= 3 else 0.0
    cap    = max(RET_CAP_MIN, RET_CAP_MULT * sigma)

    # шаги модель→последовательность приращений
    prev = float(last_price)
    raw_steps = []
    for y in pred_values:
        y = float(y)
        r = (y - prev) / max(prev, 1e-12)
        r = float(np.clip(r, -cap, cap))
        raw_steps.append(r)
        prev = prev * (1.0 + r)

    # EMA + затухание по горизонту + лёгкое центрирование (убираем «ползучий оптимизм»)
    out_steps, ema = [], 0.0
    L = max(1, len(raw_steps))
    mean_bias = float(np.mean(raw_steps))
    for i, r in enumerate(raw_steps):
        r = r - 0.5*mean_bias  # центрирование
        ema = CALIB_EMA_ALPHA * r + (1.0 - CALIB_EMA_ALPHA) * ema
        shrink = 1.0 - (1.0 - CALIB_SHRINK_LONG) * (i / (L - 1 if L > 1 else 1))
        out_steps.append(ema * shrink)

    out = []
    p = float(last_price)
    for r in out_steps:
        p = p * (1.0 + r)
        out.append(float(p))
    return out

def build_phantoms(recent_candles, pred_closes, first_ts, first_open,
                   atr_n=PHANTOM_ATR_N, k=PHANTOM_ATR_K):
    """
    Строгие фантомы: каждая 1m-свеча точно следует прогнозу.
    OPEN_i   = CLOSE_{i-1}
    CLOSE_i  = прогноз[i]
    HIGH/LOW = max/min(OPEN_i, CLOSE_i) — т.е. без искусственных фитилей.
    """
    if not pred_closes:
        return []

    ts = float(first_ts)
    o  = float(first_open)
    out = []
    for c_raw in pred_closes:
        c = float(c_raw)
        hi = max(o, c)
        lo = min(o, c)
        out.append((ts, o, hi, lo, c))
        o = c
        ts += 60.0
    return out

# ------------------------- GUI базовые --------------------
class GUIElement:
    def __init__(self, rect): self.rect=rect
    def handle_event(self,e): return False
    def update(self,dt): pass
    def draw(self,surf): pass

class TextInput(GUIElement):
    def __init__(self, rect, font, placeholder="...", on_enter=None):
        super().__init__(rect); self.font=font; self.text=""; self.active=False
        self.placeholder=placeholder; self.on_enter=on_enter
    def handle_event(self,e):
        if e.type==pygame.MOUSEBUTTONDOWN:
            self.active = self.rect.collidepoint(e.pos); return self.active
        if e.type==pygame.KEYDOWN and self.active:
            if e.key==pygame.K_BACKSPACE: self.text=self.text[:-1]
            elif e.key==pygame.K_RETURN and self.on_enter: self.on_enter(self.text)
            else:
                ch=e.unicode
                if ch: self.text+=ch
            return True
        return False
    def set_text(self,t): self.text=t
    def draw(self,s):
        pygame.draw.rect(s, (50,50,70) if self.active else (40,40,55), self.rect, border_radius=4)
        txt = self.font.render(self.text,True,COLOR_TEXT) if self.text else \
              self.font.render(self.placeholder,True,COLOR_HINT)
        s.blit(txt,(self.rect.x+6, self.rect.y+(self.rect.height-txt.get_height())//2))

class Button(GUIElement):
    def __init__(self, rect, font, text, cb): super().__init__(rect); self.font=font; self.text=text; self.cb=cb
    def handle_event(self,e):
        if e.type==pygame.MOUSEBUTTONDOWN and e.button==1 and self.rect.collidepoint(e.pos):
            if self.cb: self.cb(); return True
        return False
    def draw(self,s):
        pygame.draw.rect(s,(60,60,75),self.rect,border_radius=4)
        t=self.font.render(self.text,True,COLOR_TEXT)
        s.blit(t,(self.rect.centerx-t.get_width()//2, self.rect.centery-t.get_height()//2))

class Checkbox(GUIElement):
    def __init__(self, rect, font, label, on_toggle=None):
        super().__init__(rect); self.font=font; self.label=label; self.checked=False; self.on_toggle=on_toggle
    def handle_event(self,e):
        if e.type==pygame.MOUSEBUTTONDOWN and e.button==1 and self.rect.collidepoint(e.pos):
            self.checked=not self.checked
            if self.on_toggle: self.on_toggle(self.checked)
            return True
        return False
    def draw(self,s):
        pygame.draw.rect(s,(45,45,60),self.rect,border_radius=4)
        box=pygame.Rect(self.rect.x+5,self.rect.y+4,14,14); pygame.draw.rect(s,(220,220,220),box,1)
        if self.checked:
            pygame.draw.line(s,(0,255,120),(box.x+2,box.y+7),(box.x+5,box.y+11),2)
            pygame.draw.line(s,(0,255,120),(box.x+5,box.y+11),(box.x+11,box.y+2),2)
        t=self.font.render(self.label,True,COLOR_TEXT)
        s.blit(t,(box.right+4, self.rect.y+(self.rect.height-t.get_height())//2))

class PeriodSelector(GUIElement):
    def __init__(self, rect, font, options, on_change=None):
        super().__init__(rect); self.font=font; self.options=options; self.on_change=on_change
        self.opened=False; self.current_index=0
    @property
    def current_value(self): return self.options[self.current_index][1]
    def handle_event(self,e):
        if e.type==pygame.MOUSEBUTTONDOWN and e.button==1:
            if self.rect.collidepoint(e.pos): self.opened=not self.opened; return True
            if self.opened:
                box=pygame.Rect(self.rect.x,self.rect.bottom,self.rect.width, len(self.options)*22)
                if box.collidepoint(e.pos):
                    idx=(e.pos[1]-self.rect.bottom)//22
                    if 0<=idx<len(self.options):
                        self.current_index=idx; self.opened=False
                        if self.on_change: self.on_change(self.current_value)
                        return True
                else: self.opened=False
        return False
    def force_close(self): self.opened=False
    def draw(self,s):
        pygame.draw.rect(s,(50,50,70),self.rect,border_radius=4)
        t=self.font.render(self.options[self.current_index][0],True,COLOR_TEXT)
        s.blit(t,(self.rect.x+6, self.rect.y+(self.rect.height-t.get_height())//2))
    def draw_popup(self,s):
        if not self.opened: return
        h=len(self.options)*22; pygame.draw.rect(s,(30,30,40),(self.rect.x,self.rect.bottom,self.rect.width,h),border_radius=4)
        for i,(label,_) in enumerate(self.options):
            t=self.font.render(label,True,(230,230,230)); s.blit(t,(self.rect.x+4, self.rect.bottom+2+i*22))

class DropdownList(GUIElement):
    def __init__(self, x,y,w,item_h,font,screen_h,on_select=None):
        super().__init__(pygame.Rect(x,y,w,item_h)); self.font=font; self.sh=screen_h; self.ih=item_h
        self.on_select=on_select; self.items=[]; self.visible=False; self.scroll=0
    def set_items(self,items): self.items=items; self.scroll=0
    def hit_test(self,pos):
        if not self.visible: return False
        max_h=self.sh-self.rect.y-10; max_vis=max(1, max_h//self.ih)
        h=min(len(self.items)-self.scroll, max_vis)*self.ih
        return pygame.Rect(self.rect.x,self.rect.y,self.rect.width,h).collidepoint(pos)
    def handle_event(self,e):
        if not self.visible: return False
        max_h=self.sh-self.rect.y-10; max_vis=max(1, max_h//self.ih)
        visible=self.items[self.scroll:self.scroll+max_vis]
        area=pygame.Rect(self.rect.x,self.rect.y,self.rect.width,len(visible)*self.ih)
        if e.type==pygame.MOUSEBUTTONDOWN and e.button in (4,5) and area.collidepoint(e.pos):
            if e.button==4: self.scroll=max(0,self.scroll-1)
            else: self.scroll=min(max(0,len(self.items)-max_vis), self.scroll+1)
            return True
        if e.type==pygame.MOUSEBUTTONDOWN and e.button==1 and area.collidepoint(e.pos):
            idx=(e.pos[1]-self.rect.y)//self.ih; i=self.scroll+idx
            if 0<=i<len(self.items) and self.on_select: self.on_select(self.items[i]); return True
        return False
    def draw(self,s):
        if not self.visible: return
        max_h=self.sh-self.rect.y-10; max_vis=max(1,max_h//self.ih)
        visible=self.items[self.scroll:self.scroll+max_vis]
        h=len(visible)*self.ih; pygame.draw.rect(s,(35,35,45),(self.rect.x,self.rect.y,self.rect.width,h),border_radius=4)
        for i,item in enumerate(visible):
            t=self.font.render(item,True,(220,220,220)); s.blit(t,(self.rect.x+6,self.rect.y+2+i*self.ih))

# ------------------------- Агрегация свечей ---------------
def aggregate_candles(candles, minutes):
    """Отрисовочная агрегация в N-мин. свечи (OHLC), без записи в кэш."""
    if minutes<=1: return candles
    res=[]; bucket=None
    step=minutes*60
    for ts,o,h,l,c,is_pre in candles:
        key = floor(ts/step)*step
        if (bucket is None) or (key!=bucket["key"]):
            if bucket is not None:
                res.append((bucket["key"], bucket["o"], bucket["h"], bucket["l"], bucket["c"], is_pre))
            bucket={"key":key,"o":o,"h":h,"l":l,"c":c}
        else:
            bucket["h"]=max(bucket["h"],h); bucket["l"]=min(bucket["l"],l); bucket["c"]=c
    if bucket is not None: res.append((bucket["key"],bucket["o"],bucket["h"],bucket["l"],bucket["c"], True))
    return res

def choose_agg_minutes(px_per_candle):
    """
    Ширина 1m-свечи в пикселях -> рекомендуемая агрегация, до 7 дней.
    """
    if px_per_candle >= 8.0:   return 1        # 1 м
    if px_per_candle >= 4.0:   return 5        # 5 м
    if px_per_candle >= 2.0:   return 15       # 15 м
    if px_per_candle >= 1.2:   return 30       # 30 м
    if px_per_candle >= 0.7:   return 60       # 1 ч
    if px_per_candle >= 0.4:   return 240      # 4 ч
    if px_per_candle >= 0.25:  return 720      # 12 ч
    if px_per_candle >= 0.15:  return 1440     # 1 д
    if px_per_candle >= 0.10:  return 4320     # 3 д
    return 10080                                # 7 д

# ------------------------- Свечной график -----------------
class CandlesChart(GUIElement):
    def __init__(self, rect, font_small, state):
        super().__init__(rect); self.font_small=font_small; self.state=state
        self.seconds_per_screen=180.0; self.x_start=0.0
        self.dragging=False; self.drag_x0=0; self.drag_off0=0.0; self.user_pan=False
        self.hover_candle=None
    def reset_view(self): self.seconds_per_screen=180.0; self.x_start=0.0; self.user_pan=False

    def handle_event(self,e):
        if e.type==pygame.MOUSEBUTTONDOWN and self.rect.collidepoint(e.pos):
            # зум колесом к курсору
            if e.button in (4,5):
                mx=e.pos[0]; rel=max(0,min(1,(mx-self.rect.left)/self.rect.width))
                t_at = self.x_start + rel*self.seconds_per_screen
                new = max(30.0, self.seconds_per_screen*(0.8 if e.button==4 else 1.25))
                new = min(new, 6*24*3600.0)
                self.seconds_per_screen=new; self.x_start = max(0.0, t_at-rel*new); self.user_pan=True; return True
            # перетаскивание ЛКМ
            if e.button==1: self.dragging=True; self.drag_x0=e.pos[0]; self.drag_off0=self.x_start; return True
        if e.type==pygame.MOUSEBUTTONUP and e.button==1 and self.dragging:
            self.dragging=False; return True
        if e.type==pygame.MOUSEMOTION and self.dragging:
            dx=e.pos[0]-self.drag_x0; spp=self.seconds_per_screen/self.rect.width
            self.x_start=max(0.0, self.drag_off0 - dx*spp); self.user_pan=True; return True
        return False

    def update(self,dt,allow_keys=True):
        with self.state["lock"]:
            candles=list(self.state["data"]); base=self.state["base_time"]
        if candles and not self.user_pan and base is not None:
            last_open=candles[-1][0]; last_close=last_open+60
            now_rel=last_close-base; self.x_start=max(0.0, now_rel-self.seconds_per_screen)

    # утилиты отрисовки
    def _draw_dashed_v(self,s,x,y1,y2,color=(255,255,255),dash=6,gap=4):
        y=y1
        while y<y2:
            y2_ = min(y+dash,y2); pygame.draw.line(s,color,(x,y),(x,y2_),1); y += dash+gap
    def _fmt_gap(self,secs):
        s=int(secs); d=s//86400; s%=86400; h=s//3600; s%=3600; m=s//60; s%=60
        parts=[];
        if d: parts.append(f"{d}д")
        if h: parts.append(f"{h}ч")
        if m: parts.append(f"{m}м")
        if not parts: parts.append(f"{s}с")
        return "разрыв " + " ".join(parts)
    def _label_box(self,s,x,y,text):
        t=self.font_small.render(text,True,(20,20,20))
        w=t.get_width()+8; h=t.get_height()+4
        rx=int(x); ry=int(y-h//2)
        pygame.draw.rect(s,(245,245,245),(rx,ry,w,h))
        pygame.draw.rect(s,(255,255,255),(rx,ry,w,h),1)
        s.blit(t,(rx+4, ry+(h-t.get_height())//2))

    def draw(self, surf):
        pygame.draw.rect(surf, (15, 16, 22), self.rect)
        pygame.draw.rect(surf, (60, 60, 80), self.rect, 1)

        with self.state["lock"]:
            candles = list(self.state["data"]);
            base = self.state["base_time"]
            trades = list(self.state.get("ai_trades", []))
            hover_id = self.state.get("hover_trade_id")
            exch = self.state.get("exchange", DEFAULT_EXCH)
            events = list(self.state.get("ai_events", []))
            hover_event_id = self.state.get("hover_event_id")

        if not candles or base is None:
            return
        candles = dedupe_candles(candles)

        # видимая область/масштаб
        v0, v1 = self.x_start, self.x_start + self.seconds_per_screen
        px_per_sec = self.rect.width / (v1 - v0)
        px_per_1m = 60 * px_per_sec
        agg_min = choose_agg_minutes(px_per_1m)
        draw_candles = aggregate_candles(candles, agg_min)
        expected_step = agg_min * 60.0

        # видимые свечи
        visible = []
        for c in draw_candles:
            st = c[0] - base;
            en = st + agg_min * 60
            if en >= v0 and st <= v1: visible.append(c)
        if not visible:
            visible = draw_candles[-200:]

        highs = [c[2] for c in visible];
        lows = [c[3] for c in visible]

        # наведенная сделка
        hovered = None
        if hover_id is not None:
            for t in trades:
                if t["id"] == hover_id:
                    hovered = t;
                    break

        extra_prices = [];
        phantoms = []
        if hovered is not None:
            e, be, tp, sl = trade_levels(hovered, exch)
            extra_prices += [e, be, tp, sl]
            phantoms = hovered.get("phantoms", [])
            for p in phantoms: extra_prices += [p[2], p[3]]

        if extra_prices:
            highs.append(max(extra_prices));
            lows.append(min(extra_prices))
        pmax, pmin = max(highs), min(lows)
        if abs(pmax - pmin) < 1e-12:
            pmax += 0.5;
            pmin -= 0.5

        def y_from(p):
            n = (p - pmin) / (pmax - pmin)
            return self.rect.bottom - n * self.rect.height

        # горизонтальные цены
        for i in range(5):
            yy = self.rect.top + i * (self.rect.height / 4.0)
            pygame.draw.line(surf, (48, 48, 54), (self.rect.left, yy), (self.rect.right, yy), 1)
            price = pmax - (pmax - pmin) * (i / 4.0)
            tt = self.font_small.render(f"{price:.6f}", True, (180, 180, 190))
            surf.blit(tt, (self.rect.right - 120, yy - 10))

        # вертикальные время
        for i in range(7):
            xx = self.rect.left + i * (self.rect.width / 6.0)
            pygame.draw.line(surf, (40, 40, 46), (xx, self.rect.top), (xx, self.rect.bottom), 1)
            sec = v0 + (v1 - v0) * (i / 6.0)
            ts_abs = base + sec
            label = time.strftime("%d.%m %H:%M", time.localtime(ts_abs))
            tt = self.font_small.render(label, True, (160, 160, 170))
            surf.blit(tt, (xx + 2, self.rect.bottom - 18))

        # подсветка span обучения/дообучения
        if hover_event_id is not None and base is not None:
            ev = next((x for x in events if x["id"] == hover_event_id), None)
            if ev is not None:
                x1 = self.rect.left + ((ev["start_ts"] - base) - v0) * px_per_sec
                x2 = self.rect.left + (((ev["end_ts"] + 60.0) - base) - v0) * px_per_sec
                x1c = max(self.rect.left, int(x1))
                x2c = min(self.rect.right, int(x2))
                if x2c > x1c:
                    overlay = pygame.Surface((x2c - x1c, self.rect.height), pygame.SRCALPHA)
                    if ev["type"] == "train":
                        rgb = (80, 160, 255, 50); label = "Обучение"
                    elif ev["type"] == "refit":
                        rgb = (180, 120, 255, 60); label = "Дообучение"
                    else:
                        rgb = (150, 150, 150, 40); label = "Загрузка"
                    overlay.fill(rgb);
                    surf.blit(overlay, (x1c, self.rect.top))
                    cap = f"{label}: {time.strftime('%d.%m %H:%M', time.localtime(ev['start_ts']))} → {time.strftime('%d.%m %H:%M', time.localtime(ev['end_ts']))}"
                    self._label_box(surf, max(self.rect.left + 8, x1c + 6), self.rect.top + 34, cap)

        # свечи
        self.hover_candle = None
        mx, my = pygame.mouse.get_pos()
        prev_ts = None;
        prev_x_end = None
        for c in visible:
            ts_open, o, h, l, cl, _ = c
            st_rel = ts_open - base
            x = self.rect.left + (st_rel - v0) * px_per_sec
            w = max(2, int(agg_min * 60 * px_per_sec) - 2)
            y_h, y_l, y_o, y_c = y_from(h), y_from(l), y_from(o), y_from(cl)

            # реальные разрывы
            if prev_ts is not None and prev_x_end is not None:
                diff = ts_open - prev_ts
                excess = diff - expected_step
                if excess > 60.0:
                    x1 = int(prev_x_end);
                    x2 = int(x)
                    self._draw_dashed_v(surf, x1, self.rect.top, self.rect.bottom, (255, 180, 180))
                    self._draw_dashed_v(surf, x2, self.rect.top, self.rect.bottom, (255, 180, 180))
                    mid = (x1 + x2) // 2
                    t = self.font_small.render(self._fmt_gap(excess), True, (255, 150, 150))
                    tx = max(self.rect.left + 6, min(self.rect.right - 6 - t.get_width(), mid - t.get_width() // 2))
                    surf.blit(t, (tx, self.rect.top + 6))

            col = (0, 190, 90) if cl >= o else (230, 70, 70)
            pygame.draw.line(surf, (215, 215, 215), (x + w // 2, y_h), (x + w // 2, y_l), 1)
            top = min(y_o, y_c);
            h_body = max(1, abs(y_c - y_o))
            pygame.draw.rect(surf, col, (x, top, w, h_body))

            r = pygame.Rect(x, min(y_l, y_h), w, max(4, abs(y_l - y_h)))
            if r.collidepoint(mx, my):
                self.hover_candle = {"candle": c, "x": x, "y": y_c}

            prev_ts = ts_open;
            prev_x_end = x + w

        # уровни и вертикальные метки при наведении на сделку
        if hovered is not None:
            entry=hovered["entry_price"]
            prof = EXCH_PROFILES.get(exch, EXCH_PROFILES[DEFAULT_EXCH])
            fee_open, fee_close = prof["fee_open"], prof["fee_close"]

            if hovered["direction"]=="long":
                be=entry*(1+fee_open+fee_close)
                tp=entry*(1+hovered["target_pct"])
                sl=entry*(1-hovered["stop_pct"])
            else:
                be=entry*(1-fee_open-fee_close)
                tp=entry*(1-hovered["target_pct"])
                sl=entry*(1+hovered["stop_pct"])

            # горизонтальные уровни
            for val,name in [(entry,"Вход"),(be,"Безубыток"),(tp,"Цель"),(sl,"Стоп")]:
                y=y_from(val)
                if self.rect.top<=y<=self.rect.bottom:
                    pygame.draw.line(surf,(255,255,255),(self.rect.left,y),(self.rect.right,y),1)
                    self._label_box(surf,self.rect.left+6,y,name)

            # вертикаль «Вход»
            x_in = self.rect.left + ((hovered["open_ts"] - base) - v0) * px_per_sec
            if self.rect.left-10<=x_in<=self.rect.right+10:
                self._draw_dashed_v(surf,int(x_in),self.rect.top,self.rect.bottom,(255,255,255))

            # вертикаль «Ожид. закрытие» — только пока сделка открыта
            if hovered.get("status") == "open":
                exp_close = float(hovered.get("expected_close_ts", hovered["open_ts"] + hovered.get("max_hold_sec", 0)))
                x_out = self.rect.left + ((exp_close - base) - v0) * px_per_sec
                if self.rect.left-10<=x_out<=self.rect.right+10:
                    self._draw_dashed_v(surf,int(x_out),self.rect.top,self.rect.bottom,(255,255,255))
                    self._label_box(surf, min(self.rect.right-160, max(self.rect.left+6, int(x_out)+6)),
                                    self.rect.top+18, "Ожид. закрытие")

            # вертикаль «Закрытие» — если сделка уже закрыта
            if hovered.get("status") != "open" and hovered.get("close_ts") is not None:
                x_closed = self.rect.left + ((float(hovered["close_ts"]) - base) - v0) * px_per_sec
                if self.rect.left-10<=x_closed<=self.rect.right+10:
                    self._draw_dashed_v(surf,int(x_closed),self.rect.top,self.rect.bottom,(255,255,255))
                    self._label_box(surf, min(self.rect.right-140, max(self.rect.left+6, int(x_closed)+6)),
                                    self.rect.top+18, "Закрытие")

            # фантомные свечи (строгие — тело = прогнозу)
            ph_list = hovered.get("phantoms", [])
            for p in ph_list:
                ts_open,o,h,l,cl = p
                xr=self.rect.left + ((ts_open-base) - v0)*px_per_sec
                if xr < self.rect.left-20 or xr>self.rect.right+20:
                    continue
                w = max(2, int(60*px_per_sec)-2)
                y_h,y_l,y_o,y_c=y_from(h),y_from(l),y_from(o),y_from(cl)
                pygame.draw.line(surf,(120,190,255),(xr+w//2,y_h),(xr+w//2,y_l),1)
                top=min(y_o,y_c); hb=max(1, abs(y_c-y_o))
                s2=pygame.Surface((w,int(hb)), pygame.SRCALPHA); s2.fill((120,190,255,150))
                surf.blit(s2,(xr, top))


        # тултип по свече
        if self.hover_candle:
            ts_open, o, h, l, cl, _ = self.hover_candle["candle"]
            lines = [time.strftime("Время: %d.%m %H:%M", time.localtime(ts_open)),
                     f"Откр.: {o:.6f}", f"Макс.: {h:.6f}", f"Мин.: {l:.6f}", f"Закр.: {cl:.6f}"]
            pad = 4
            surfaces = [self.font_small.render(t, True, (0, 0, 0)) for t in lines]
            w = max(x.get_width() for x in surfaces) + 2 * pad
            h = len(surfaces) * (self.font_small.get_height() + 2) + 2 * pad
            tx = min(max(self.hover_candle["x"] + 10, self.rect.left + 6), self.rect.right - 6 - w)
            ty = max(self.rect.top + 6, min(self.hover_candle["y"] - h - 10, self.rect.bottom - 6 - h))
            pygame.draw.rect(surf, (240, 240, 240), (tx, ty, w, h), border_radius=4)
            y = ty + pad
            for t in surfaces:
                surf.blit(t, (tx + pad, y));
                y += self.font_small.get_height() + 2


# ------------------------- Журналы ------------------------
def wrap_text(font, text, max_w):
    words=text.split(); lines=[]; cur=""
    for w in words:
        t=(cur+" "+w).strip()
        if font.size(t)[0]<=max_w: cur=t
        else:
            if cur: lines.append(cur)
            cur=w
    if cur: lines.append(cur)
    return lines

class AIStatusLog(GUIElement):
    def __init__(self, rect, font, small_font, state):
        super().__init__(rect); self.font=font; self.small=small_font; self.state=state
        self.scroll=0; self.header_h=44
    def handle_event(self,e):
        logs=pygame.Rect(self.rect.x,self.rect.y+self.header_h,self.rect.width,self.rect.height-self.header_h)
        if e.type==pygame.MOUSEBUTTONDOWN and e.button in (4,5) and logs.collidepoint(e.pos):
            self.scroll=max(0,self.scroll-1) if e.button==4 else self.scroll+1; return True
        return False
    def draw(self,s):
        pygame.draw.rect(s,(22,23,32),self.rect); pygame.draw.rect(s,(80,80,110),self.rect,1)
        with self.state["lock"]:
            status=self.state.get("ai_status",""); debug=list(self.state.get("ai_debug",[]))
        y=self.rect.y+4; max_w=self.rect.width-10
        for line in wrap_text(self.small, status, max_w)[:2]:
            t=self.small.render(line,True,(225,225,235)); s.blit(t,(self.rect.x+4,y)); y+=self.small.get_height()+2
        pygame.draw.line(s,(90,90,115),(self.rect.x+2,self.rect.y+self.header_h-1),
                         (self.rect.right-2,self.rect.y+self.header_h-1),1)
        y=self.rect.y+self.header_h+2; y_max=self.rect.bottom-4
        start=self.scroll
        for item in debug[start:]:
            for ln in wrap_text(self.small, item, max_w):
                if y>y_max: return
                t=self.small.render(ln,True,(165,165,220)); s.blit(t,(self.rect.x+4,y)); y+=self.small.get_height()+2

class AILog(GUIElement):
    """
    Пиксельная прокрутка, аккуратный hover, без обрезания списка.
    Колёсико мыши — плавно листает; каждая карточка может быть любой высоты.
    """
    def __init__(self, rect, font, small_font, state, balance_input):
        super().__init__(rect)
        self.font = font
        self.small = small_font
        self.state = state
        self.balance_input = balance_input
        self.inner_top = 28  # место под "Баланс:"
        self.scroll_px = 0   # текущий сдвиг содержимого в пикселях
        self._last_layout = []   # кэш разметки для hover
        self._content_h = 0

    def _fmt(self, tr):
        t = time.strftime("%H:%M", time.localtime(tr["open_ts"]))
        side = "ЛОНГ" if tr["direction"] == "long" else "ШОРТ"
        status = tr.get("status", "open")
        pnl = tr.get("pnl", 0.0)
        be = "BE"  # кратко, уровень безубытка рисуем на графике
        return (f"[{t}] {tr['symbol']} • {side} • ставка {tr['stake']:.2f} • "
                f"вход {tr['entry_price']:.6f} | {be} • "
                f"TP {tr['target_pct']*100:.2f}% | SL {tr['stop_pct']*100:.2f}% • "
                f"горизонт {int(round(tr['max_hold_sec']/60.0))} мин • "
                f"статус: {status} {pnl:+.2f}")

    def _layout(self, trades, max_w):
        """
        Делает разметку всех карточек: [(tr, lines, height), ...] в обратном порядке (снизу — новые).
        """
        blocks = []
        lh = self.small.get_height() + 3
        for tr in trades[::-1]:
            lines = wrap_text(self.small, self._fmt(tr), max_w)
            h = len(lines) * lh + 4  # +паддинг
            blocks.append((tr, lines, h))
        content_h = sum(h for _,_,h in blocks)
        return blocks, content_h, lh

    def handle_event(self, e):
        # передадим фокус полю "Баланс"
        if self.balance_input.handle_event(e):
            return True

        # прокрутка колёсиком
        if e.type == pygame.MOUSEBUTTONDOWN and e.button in (4, 5) and self.rect.collidepoint(e.pos):
            with self.state["lock"]:
                trades = list(self.state.get("ai_trades", []))
            max_w = self.rect.width - 10
            blocks, content_h, lh = self._layout(trades, max_w)
            view_h = self.rect.height - self.inner_top - 6
            step = lh * 2  # шаг прокрутки ~две строки
            if e.button == 4:
                self.scroll_px = max(0, self.scroll_px - step)
            else:
                self.scroll_px = min(max(0, content_h - view_h), self.scroll_px + step)
            return True

        # hover по карточке — выставим hover_trade_id
        mx, my = pygame.mouse.get_pos()
        if self.rect.collidepoint((mx, my)):
            with self.state["lock"]:
                trades = list(self.state.get("ai_trades", []))
            max_w = self.rect.width - 10
            blocks, content_h, lh = self._layout(trades, max_w)
            view_h = self.rect.height - self.inner_top - 6

            # зажим границ скролла (если список уменьшился/увеличился)
            self.scroll_px = min(max(0, content_h - view_h), self.scroll_px)

            # определим стартовый блок по scroll_px
            offset = self.scroll_px
            i = 0
            while i < len(blocks) and offset >= blocks[i][2]:
                offset -= blocks[i][2]
                i += 1
            y = self.rect.y + self.inner_top + 4 - offset

            hovered = None
            for j in range(i, len(blocks)):
                tr, lines, h = blocks[j]
                box = pygame.Rect(self.rect.x + 2, y, self.rect.width - 4, h)
                if box.collidepoint((mx, my)):
                    hovered = tr["id"]
                    break
                y += h
                if y > self.rect.bottom:
                    break
            with self.state["lock"]:
                self.state["hover_trade_id"] = hovered
            return False
        else:
            with self.state["lock"]:
                self.state["hover_trade_id"] = None
        return False

    def draw(self, s):
        # фон и рамка
        pygame.draw.rect(s, (25, 26, 35), self.rect)
        pygame.draw.rect(s, (70, 70, 100), self.rect, 1)

        # заголовок и поле "Баланс"
        s.blit(self.small.render("Баланс:", True, COLOR_TEXT), (self.rect.x + 6, self.rect.y + 5))
        self.balance_input.draw(s)

        # данные
        with self.state["lock"]:
            trades = list(self.state.get("ai_trades", []))
            hovered_id = self.state.get("hover_trade_id")

        max_w = self.rect.width - 10
        blocks, content_h, lh = self._layout(trades, max_w)
        self._last_layout = blocks
        self._content_h = content_h

        view_top = self.rect.y + self.inner_top + 4
        view_h = self.rect.height - self.inner_top - 6

        # зажимаем скролл в допустимые рамки
        self.scroll_px = min(max(0, content_h - view_h), self.scroll_px)

        # вычисляем стартовый блок по scroll_px
        offset = self.scroll_px
        i = 0
        while i < len(blocks) and offset >= blocks[i][2]:
            offset -= blocks[i][2]
            i += 1
        y = view_top - offset

        # отрисовка видимых блоков
        for j in range(i, len(blocks)):
            tr, lines, h = blocks[j]
            if y > self.rect.bottom:
                break
            color = (200, 200, 200)
            if tr.get("status") == "прибыль":
                color = (0, 200, 120)
            elif tr.get("status") == "убыток":
                color = (230, 70, 70)

            # hover-подсветка
            if hovered_id == tr["id"]:
                pygame.draw.rect(s, (40, 40, 60), (self.rect.x + 2, y, self.rect.width - 4, h))

            yy = y + 2
            for ln in lines:
                t = self.small.render(ln, True, color)
                s.blit(t, (self.rect.x + 5, yy))
                yy += lh
            y += h


# ------------------------- Логика AI ----------------------
def ai_log(state,*lines):
    stamp=time.strftime("%H:%M:%S")
    with state["lock"]:
        dbg=state.get("ai_debug",[])
        for ln in lines: dbg.insert(0,f"[{stamp}] {ln}")
        state["ai_debug"]=dbg[:120]

def _push_ai_event(state, ev):
    """ev: {"type": "train|refit|load", "symbol": str, "start_ts": float, "end_ts": float, "epochs": int}"""
    if ev["start_ts"] >= ev["end_ts"]: return
    with state["lock"]:
        # защита от дублей: тот же тип, символ и точный span
        for e in state.get("ai_events", []):
            if e["type"]==ev["type"] and e["symbol"]==ev["symbol"] and abs(e["start_ts"]-ev["start_ts"])<1 and abs(e["end_ts"]-ev["end_ts"])<1:
                return
        ev = dict(ev)
        ev["id"] = state.get("ai_event_next_id", 1)
        state["ai_event_next_id"] = ev["id"] + 1
        arr = state.get("ai_events", [])
        arr.append(ev)
        state["ai_events"] = arr

def evaluate_trades(state):
    now = time.time()
    with state["lock"]:
        candles = list(state.get("data", []))
        trades  = list(state.get("ai_trades", []))
        balance = float(state.get("ai_balance", 1000.0))
        exch    = state.get("exchange", DEFAULT_EXCH)
        sym     = state.get("current_symbol")

    if not candles:
        return

    last_px = float(candles[-1][4])
    minute_close_ts = float(int(candles[-1][0]) + 60)

    updated = False
    for t in trades:
        if t.get("status") != "open":
            continue

        entry   = float(t["entry_price"])
        stake   = float(t["stake"])
        dirlong = (t["direction"] == "long")
        elapsed = now - float(t["open_ts"])

        prof = EXCH_PROFILES.get(exch, EXCH_PROFILES[DEFAULT_EXCH])
        fee_open, fee_close = float(prof["fee_open"]), float(prof["fee_close"])
        tp_pct = float(t["target_pct"]); sl_pct = float(t["stop_pct"])

        if dirlong:
            be = entry * (1.0 + fee_open + fee_close)
            tp = entry * (1.0 + tp_pct)
            sl = entry * (1.0 - sl_pct)
        else:
            be = entry * (1.0 - fee_open - fee_close)
            tp = entry * (1.0 - tp_pct)
            sl = entry * (1.0 + sl_pct)

        reason = None
        close_price = last_px

        if dirlong and last_px <= sl:           reason = "sl"
        elif (not dirlong) and last_px >= sl:   reason = "sl"
        elif dirlong and last_px >= tp:         reason = "tp"
        elif (not dirlong) and last_px <= tp:   reason = "tp"
        elif elapsed >= float(t["max_hold_sec"]): reason = "time"

        if reason is not None:
            pnl = stake * ((close_price - entry) / max(entry, 1e-12)) if dirlong \
                  else stake * ((entry - close_price) / max(entry, 1e-12))

            t["status"]     = "прибыль" if pnl >= 0 else "убыток"
            t["exit_price"] = float(close_price)
            t["pnl"]        = float(pnl)
            t["close_ts"]   = minute_close_ts

            balance += stake + pnl
            updated = True

            if reason == "tp":
                ai_log(state, f"Закрытие по TP @ {close_price:.6f} • pnl {pnl:+.2f}")
            elif reason == "sl":
                ai_log(state, f"Закрытие по SL @ {close_price:.6f} • pnl {pnl:+.2f}")
            else:
                ai_log(state, f"Закрытие по времени @ {close_price:.6f} • pnl {pnl:+.2f}")

    if updated:
        with state["lock"]:
            state["ai_trades"]  = trades[-MAX_TRADES_KEEP:]
            state["ai_balance"] = balance
            state["ai_status"]  = "Сделка закрыта"
            state["ai_next_time"] = time.time() + 10.0

        # сохраняем сделки этой пары
        if sym:
            save_trades(sym, trades)

def run_ai(state):
    with state["lock"]:
        state["ai_busy"] = True
    try:
        # --- текущее состояние
        with state["lock"]:
            sym        = state.get("current_symbol")
            trades     = list(state.get("ai_trades", []))
            cool_until = float(state.get("ai_cooldown_until", 0.0))
        now = time.time()

        if now < cool_until:
            with state["lock"]:
                state["ai_status"]   = f"Кулдаун до {time.strftime('%H:%M', time.localtime(cool_until))}"
                state["ai_next_time"] = cool_until
            return

        if not sym:
            with state["lock"]:
                state["ai_status"]   = "Выберите пару"
                state["ai_next_time"] = time.time() + 30
            return

        if any(t for t in trades if t.get("status") == "open"):
            with state["lock"]:
                state["ai_status"]   = "Есть открытая сделка"
                state["ai_next_time"] = time.time() + 20
            return

        if not DARTS_AVAILABLE:
            with state["lock"]:
                state["ai_status"] = f"Darts не установлен: {DARTS_ERR}"
            return

        # --- данные
        obj,_  = load_cache(sym)
        all_c  = obj.get("candles", [])
        if len(all_c) < AI_MIN_CANDLES:
            with state["lock"]:
                state["ai_status"]   = f"Мало данных ({len(all_c)}/{AI_MIN_CANDLES})"
                state["ai_next_time"] = time.time() + 30
            return

        train = all_c[-AI_MAX_TRAIN_CANDLES:]
        last_price = float(train[-1][4])
        last_bar_ts = float(train[-1][0])

        # --- модель и прогноз
        model = MODEL_REG.get(sym, AI_INPUT_LEN, AI_PRED_HORIZON)
        try:
            fc, fitinfo = model.fit_predict(train, in_len=AI_INPUT_LEN, out_len=AI_PRED_HORIZON, always_refit=AI_ALWAYS_REFIT)
        except Exception as e:
            with state["lock"]:
                state["ai_status"]   = f"Ошибка Darts: {e}"
                state["ai_next_time"] = time.time() + 90
            ai_log(state, f"Ошибка Darts: {e}")
            return

        # информативные логи (кратко)
        if fitinfo.get("refit_done") and fitinfo.get("refit_span"):
            s,e = fitinfo["refit_span"]; mins = int(round((e-s)/60.0))+1
            ai_log(state, f"Дообучение: +{mins} свеч.")
        elif fitinfo.get("skipped_refit"):
            ai_log(state, "Модель актуальна: дообучение не требуется")

        pred_short = list(fc.univariate_values().tolist())
        pred_short_cal = calibrate_forecast(last_price, pred_short, train)

        # --- моментумы (для фильтра)
        closes = np.array([c[4] for c in train], dtype=np.float64)
        def slope_pct(window):
            if len(closes) < window + 1: return 0.0
            x = np.arange(window); y = closes[-window:]
            k = np.polyfit(x, y, 1)[0]
            return float(k / max(y[-1], 1e-12))
        mom5, mom15 = slope_pct(5), slope_pct(15)

        # --- оценка силы и горизонт
        delta_short = (pred_short_cal[-1] - last_price) / max(last_price, 1e-12)
        strength = max(abs(delta_short), abs(mom15) * AI_PRED_HORIZON)
        k_h = min(1.0, strength / 0.01)
        horizon_sec = int(AI_HOLD_MIN_SEC + (AI_HOLD_MAX_SEC - AI_HOLD_MIN_SEC) * k_h)
        horizon_min = max(1, int(round(horizon_sec / 60.0)))

        # прогноз на весь горизонт (для фантомов и направления)
        try:
            ts2 = model._series(train)
            fc2 = model.model.predict(horizon_min, series=ts2)
            pred_h = list(fc2.univariate_values().tolist())
            pred_h_cal = calibrate_forecast(last_price, pred_h, train)
        except Exception:
            pred_h_cal = (pred_short_cal + [pred_short_cal[-1]]*(horizon_min - len(pred_short_cal))) if len(pred_short_cal) < horizon_min else pred_short_cal[:horizon_min]

        delta_h = (pred_h_cal[-1] - last_price) / max(last_price, 1e-12)
        if abs(delta_h) < AI_MIN_MOVE:
            with state["lock"]:
                state["ai_status"]   = "Прогноз слабый"
                state["ai_next_time"] = time.time() + AI_NEXT_DEFAULT
            ai_log(state, f"Пропуск: прогноз слабый (Δ={delta_h*100:.2f}%)")
            return

        dir_from_forecast = "long" if delta_h > 0 else "short"

        # --- фильтр конфликта с моментумом
        sign = lambda x: (1 if x > 0 else (-1 if x < 0 else 0))
        s_pred, s_m5, s_m15 = sign(delta_h), sign(mom5), sign(mom15)

        with state["lock"]:
            conflicts = dict(state.get("ai_conflict", {}))
        force_small = False

        if (s_m5 == -s_pred) and (s_m15 == -s_pred):
            cnt = int(conflicts.get(sym, 0)) + 1
            if cnt < CONFLICT_MAX_REPEATS:
                # переназначаем запуск на конец текущей минуты
                next_check = last_bar_ts + 60.0 + CONFLICT_RECHECK_OFFSET_SEC
                with state["lock"]:
                    conflicts[sym] = cnt
                    state["ai_conflict"] = conflicts
                    state["ai_status"]    = "Конфликт прогноза и момента • жду закрытия бара"
                    state["ai_next_time"] = next_check
                ai_log(state, f"Конфликт (прогноз {dir_from_forecast}, mom5={mom5*100:.2f}%, mom15={mom15*100:.2f}%) • повторная проверка в {time.strftime('%H:%M:%S', time.localtime(next_check))}")
                return
            else:
                # 3-й конфликт подряд — входим малой позицией в сторону прогноза
                force_small = True
                with state["lock"]:
                    conflicts[sym] = 0
                    state["ai_conflict"] = conflicts
                ai_log(state, "3 конфликта подряд — вхожу малой позицией в сторону прогноза")

        else:
            # конфликта нет — сбрасываем счётчик
            if conflicts.get(sym):
                with state["lock"]:
                    conflicts[sym] = 0
                    state["ai_conflict"] = conflicts

        direction = dir_from_forecast

        # --- TP/SL по ATR + комиссии
        tail = train[-max(PHANTOM_ATR_N, 20):]
        atr = max(1e-9, np.mean([abs(c[2]-c[3]) for c in tail]) if tail else last_price*0.001)
        atr_pct = atr / max(1e-12, last_price)
        tp_pct = float(np.clip(1.2*atr_pct, AI_TARGET_MIN_PCT, max(0.006, 3.0*atr_pct)))
        sl_pct = float(np.clip(0.8*atr_pct, 0.0006, 0.012))

        with state["lock"]:
            exch = state.get("exchange", DEFAULT_EXCH)
        fees = EXCH_PROFILES.get(exch, EXCH_PROFILES[DEFAULT_EXCH])
        fee_total = float(fees["fee_open"] + fees["fee_close"])

        exp_move = max(tp_pct, abs(delta_h))
        if exp_move <= fee_total:
            with state["lock"]:
                state["ai_status"]   = "Движение меньше комиссий"
                state["ai_next_time"] = time.time() + AI_NEXT_DEFAULT
            ai_log(state, f"Пропуск: ожидаемое {exp_move*100:.2f}% ≤ комиссии {fee_total*100:.2f}%")
            return

        # --- фантомы строго по прогнозу
        open_ts = float(last_bar_ts + 60.0)
        phantoms = build_phantoms(train, pred_h_cal, open_ts, last_price)

        # --- размер позиции
        with state["lock"]:
            bal = float(state.get("ai_balance", 1000.0))
        stake = compute_position_size(bal, sl_pct)
        if force_small:
            stake = max(5.0, stake * CONFLICT_SMALL_STAKE)

        # --- создаём сделку
        created_at = time.time()
        with state["lock"]:
            trade = {
                "id": state.get("ai_next_id", 1),
                "symbol": sym,
                "direction": direction,
                "entry_price": last_price,
                "open_ts": open_ts,
                "expected_close_ts": open_ts + horizon_sec,
                "target_pct": tp_pct,
                "stop_pct":   sl_pct,
                "max_hold_sec": horizon_sec,
                "stake": stake,
                "status": "open",
                "exit_price": None,
                "pnl": 0.0,
                "forecast": pred_h_cal,
                "forecast_start_ts": open_ts,
                "phantoms": phantoms,
                "best_price": last_price,
                "created_at": created_at,
                "forecast_direction": direction,
            }
            arr = state.get("ai_trades", [])
            arr.append(trade); arr = arr[-MAX_TRADES_KEEP:]
            state["ai_trades"]  = arr
            state["ai_balance"] = bal - stake
            state["ai_next_id"] = trade["id"] + 1
            state["ai_status"]  = f"Сделка {('ЛОНГ' if direction=='long' else 'ШОРТ')} {int(round(horizon_sec/60.0))} мин"
            state["ai_next_time"] = time.time() + 30

        ai_log(state,
               f"Открываю {('лонг' if direction=='long' else 'шорт')} • ставка {stake:.2f} • "
               f"ожидаем открытие {time.strftime('%H:%M', time.localtime(open_ts))} • "
               f"TP {tp_pct*100:.2f}%, SL {sl_pct*100:.2f}% • Δпрогноза={delta_h*100:.2f}%")

        # если у тебя есть сохранение сделок — не забудь здесь дернуть persist_trades_for_symbol(state)
        try:
            persist_trades_for_symbol(state)
        except Exception:
            pass

    finally:
        with state["lock"]:
            state["ai_busy"] = False

# ------------------------- Поток цен ----------------------
class PriceFetcher(threading.Thread):
    def __init__(self, state):
        super().__init__(daemon=True)
        self.state = state
        self.running = True

    def run(self):
        while self.running:
            # --- 1) котировки
            with self.state["lock"]:
                sym = self.state.get("current_symbol")

            if sym:
                try:
                    price = float(requests.get(BINANCE_PRICE_URL.format(symbol=sym), timeout=5).json()["price"])
                    ts = time.time()
                    minute = int(ts // 60) * 60
                    with self.state["lock"]:
                        arr = self.state["data"]
                        if not arr:
                            arr.append((float(minute), price, price, price, price, False))
                            self.state["base_time"] = float(minute)
                            save_cache(sym, arr)
                        else:
                            last = arr[-1]
                            if int(last[0]) == minute:
                                _, o, h, l, c, _ = last
                                new = (last[0], o, max(h, price), min(l, price), price, False)
                                arr[-1] = new
                                save_cache(sym, arr)
                            elif minute > int(last[0]):
                                arr.append((float(minute), price, price, price, price, False))
                                save_cache(sym, arr)
                    # проверка/закрытие сделок
                    evaluate_trades(self.state)
                except Exception as e:
                    print("Цена err:", e)

            # --- 2) планировщик AI
            now = time.time()
            with self.state["lock"]:
                enabled = bool(self.state.get("ai_enabled", False))
                busy    = bool(self.state.get("ai_busy", False))
                nxt     = float(self.state.get("ai_next_time", 0.0))
                open_exists = any(t.get("status") == "open" for t in self.state.get("ai_trades", []))
                cur_status = str(self.state.get("ai_status", ""))

            if enabled and (not busy) and now >= nxt:
                # стартуем расчет
                threading.Thread(target=run_ai, args=(self.state,), daemon=True).start()
            else:
                # объясняем, почему не стартуем прямо сейчас
                if not enabled:
                    msg = "ИИ выключен"
                elif busy:
                    msg = "ИИ занят: идёт расчёт…"
                elif open_exists:
                    msg = "Есть открытая сделка — новый вход после закрытия"
                elif not sym:
                    msg = "Выберите пару"
                else:
                    remain = int(max(0, round(nxt - now)))
                    msg = f"ИИ включён, жду • запуск через {remain} с"

                with self.state["lock"]:
                    # не перетираем важные статусы об ошибках/сделках
                    if not cur_status.startswith(("Ошибка", "Сделка", "Закрытие", "Открываю", "Пропуск", "Сигнал", "Конфликт", "Движение")):
                        self.state["ai_status"] = msg

            time.sleep(1)

# ------------------------- App ----------------------------
def fetch_all_symbols():
    try:
        data=requests.get(BINANCE_ALL_TICKERS_URL,timeout=6).json()
        syms=sorted(d["symbol"] for d in data); return syms
    except Exception as e:
        print("tickers err:",e); return ["BTCUSDT","ETHUSDT","BNBUSDT"]

class BaseApp:
    def __init__(self,w,h,title,fps=60):
        pygame.init(); self.screen=pygame.display.set_mode((w,h)); pygame.display.set_caption(title)
        self.clock=pygame.time.Clock(); self.fps=fps; self.running=True
    def handle_event(self,e): pass
    def update(self,dt): pass
    def draw(self,screen): pass
    def run(self):
        while self.running:
            dt=self.clock.tick(self.fps)/1000.0
            for e in pygame.event.get():
                if e.type==pygame.QUIT: self.running=False
                else: self.handle_event(e)
            self.update(dt); self.draw(self.screen); pygame.display.flip()
        pygame.quit()

class CryptoDartsApp(BaseApp):
    def __init__(self):
        super().__init__(WIDTH, HEIGHT, "Свечной график + Darts ИИ", FPS)
        self.font  = pygame.font.SysFont("consolas", 18)
        self.small = pygame.font.SysFont("consolas", 14)

        self.state = {
            "current_symbol": None,
            "data": [],
            "base_time": None,
            "lock": threading.Lock(),

            "ai_enabled": False,
            "ai_busy": False,
            "ai_next_time": 0.0,
            "ai_status": "ИИ выключен",
            "ai_debug": [],
            "ai_trades": [],
            "ai_balance": 1000.0,
            "ai_next_id": 1,
            "hover_trade_id": None,
            "exchange": DEFAULT_EXCH,
            "ai_cooldown_until": 0.0,

            # события обучения/дообучения
            "ai_events": [],
            "ai_event_next_id": 1,
            "hover_event_id": None,
        }

        # поиск/выбор тикера
        self.search = TextInput(SEARCH_RECT, self.small, placeholder="...")
        self.all_syms = fetch_all_symbols()
        self.filtered = self.all_syms[:300]
        self.dropdown = DropdownList(10, 40, SEARCH_RECT.width, 20, self.small, HEIGHT, on_select=self._on_symbol)
        self.dropdown.set_items(self.filtered)
        self.dropdown.visible = False

        # убран PeriodSelector — период больше не выбирается пользователем

        # элементы GUI
        self.ai_check = Checkbox(AI_RECT, self.small, "ИИ", on_toggle=self._on_ai)
        self.help_btn = Button(HELP_RECT, self.small, "?", self._toggle_help)

        self.chart = CandlesChart(PLOT_RECT, self.small, self.state)

        bal_rect = pygame.Rect(TRADES_RECT.x + 70, TRADES_RECT.y + 4, 100, 20)
        self.balance_input = TextInput(bal_rect, self.small, placeholder="1000", on_enter=self._on_balance)
        self.balance_input.set_text("1000")

        self.status_log = AIStatusLog(STATUS_RECT, self.small, self.small, self.state)
        self.trades_log = AILog(TRADES_RECT, self.small, self.small, self.state, self.balance_input)

        self.show_help = False

        # поток цен
        self.fetcher = PriceFetcher(self.state)
        self.fetcher.start()

    # === callbacks ===
    def _on_balance(self, txt):
        try:
            v = float(txt.replace(",", "."))
            v = max(0.0, v)
        except:
            v = None
        with self.state["lock"]:
            if v is None:
                v = self.state.get("ai_balance", 1000.0)
            self.state["ai_balance"] = v
        self.balance_input.set_text(f"{v:.2f}")

    def _on_symbol(self, sym):
        with self.state["lock"]:
            self.state["current_symbol"] = sym

        # 7 дней истории + зашивка разрывов (как у тебя сейчас)
        ensure_history(sym, 7 * 24 * 3600, self.state)
        ensure_history(sym, 7 * 24 * 3600, self.state, only_fill_gaps=True)

        # --- загрузка сделок этой пары
        loaded = load_trades(sym)
        with self.state["lock"]:
            self.state["ai_trades"] = loaded[-MAX_TRADES_KEEP:]
            # скорректируем next_id, чтобы не было пересечений
            self.state["ai_next_id"] = next_trade_id_from(self.state["ai_trades"], self.state.get("ai_next_id", 1))

        self.chart.reset_view()
        self.dropdown.visible = False
        self.search.active = False

    def _on_ai(self, state_on: bool):
        with self.state["lock"]:
            self.state["ai_enabled"] = state_on
            if state_on:
                # запускаем немедленно
                self.state["ai_next_time"] = time.time() - 1.0
                self.state["ai_status"] = "ИИ включён, готовлюсь к запуску…"
            else:
                self.state["ai_status"] = "ИИ выключен"

    def _toggle_help(self):
        self.show_help = not self.show_help

    # === event loop integration ===
    def handle_event(self, e):
        if e.type == pygame.MOUSEBUTTONDOWN and self.show_help:
            self.show_help = False

        if self.balance_input.handle_event(e):
            return

        if self.search.handle_event(e):
            q = self.search.text.upper()
            self.filtered = [s for s in self.all_syms if q in s][:300] if q else self.all_syms[:300]
            self.dropdown.set_items(self.filtered)
            self.dropdown.visible = True
            return

        if self.help_btn.handle_event(e):
            return
        if self.ai_check.handle_event(e):
            return

        if self.dropdown.handle_event(e):
            return
        if self.status_log.handle_event(e):
            return
        if self.trades_log.handle_event(e):
            return

        # клик мимо — закрыть выпадашки
        if e.type == pygame.MOUSEBUTTONDOWN:
            if (not self.search.rect.collidepoint(e.pos)
                and not self.dropdown.hit_test(e.pos)
                and not STATUS_RECT.collidepoint(e.pos)
                and not TRADES_RECT.collidepoint(e.pos)
                and not self.balance_input.rect.collidepoint(e.pos)):
                self.dropdown.visible = False
                self.search.active = False

        # прокидываем в график, если текстовые инпуты не активны
        if not self.search.active and not self.balance_input.active:
            if self.chart.handle_event(e):
                return

        # горячие клавиши
        if e.type == pygame.KEYDOWN and e.key == pygame.K_RETURN and not self.search.active and self.filtered:
            self._on_symbol(self.filtered[0])
        if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
            self.running = False

    def update(self, dt):
        if not self.search.active:
            self.dropdown.visible = False

        allow = (not self.search.active
                 and not self.dropdown.visible
                 and not self.show_help
                 and not self.balance_input.active)

        self.chart.update(dt, allow_keys=allow)

        if not self.balance_input.active:
            with self.state["lock"]:
                bal = self.state.get("ai_balance", 1000.0)
            self.balance_input.set_text(f"{bal:.2f}")

    def draw(self, screen):
        screen.fill(COLOR_BG)

        # top bar
        self.search.draw(screen)
        self.ai_check.draw(screen)
        self.help_btn.draw(screen)

        with self.state["lock"]:
            cur = self.state.get("current_symbol")
            exch = self.state.get("exchange", DEFAULT_EXCH)
        pair = cur if cur else "—"
        t = self.font.render(pair, True, COLOR_TEXT if cur else COLOR_HINT)
        # подпись пары ставим правее поля поиска (периода больше нет)
        screen.blit(t, (SEARCH_RECT.right + 12, TOPBAR_Y + (SEARCH_RECT.height - t.get_height()) // 2))

        # main panels
        self.chart.draw(screen)
        self.status_log.draw(screen)
        self.trades_log.draw(screen)

        # dropdown
        self.dropdown.draw(screen)

        # help overlay
        if self.show_help:
            ow, oh = 620, 240
            ox = (WIDTH - RIGHT_PANEL_W - ow) // 2
            oy = (HEIGHT - oh) // 2
            panel = pygame.Surface((ow, oh))
            panel.set_alpha(230)
            panel.fill((26, 26, 36))
            screen.blit(panel, (ox, oy))
            pygame.draw.rect(screen, (120, 120, 150), (ox, oy, ow, oh), 2)
            lines = [
                "Управление",
                "• Поиск — фильтр по парам; Enter — выбрать первую",
                "• Колесо — зум к курсору; ЛКМ — перетаскивание",
                "• История: 7 дней (если кэша нет); закрытие разрывов + перезалив хвоста",
                "• ИИ — автосделка (одна одновременно), дообучение перед входом",
                "• Наведи на сделку — вход/ожид. закрытие + уровни",
                "• Наведи на строки ОБУЧЕНИЕ/ДООБУЧЕНИЕ — подсветка соответствующего диапазона",
                f"• Профиль комиссий: {EXCH_PROFILES[exch]['name']}",
            ]
            for i, ln in enumerate(lines):
                tt = self.small.render(ln, True, COLOR_TEXT)
                screen.blit(tt, (ox + 12, oy + 12 + i * 26))

def trade_levels(trade, exch_key):
    """
    Возвращает (entry, break_even, take_profit, stop) для сделки trade с учётом комиссий биржи.
    """
    entry = float(trade["entry_price"])
    tp_pct = float(trade["target_pct"])
    sl_pct = float(trade["stop_pct"])
    prof = EXCH_PROFILES.get(exch_key, EXCH_PROFILES[DEFAULT_EXCH])
    fee_open, fee_close = float(prof["fee_open"]), float(prof["fee_close"])

    if trade["direction"] == "long":
        be = entry * (1.0 + fee_open + fee_close)
        tp = entry * (1.0 + tp_pct)
        sl = entry * (1.0 - sl_pct)
    else:
        be = entry * (1.0 - fee_open - fee_close)
        tp = entry * (1.0 - tp_pct)
        sl = entry * (1.0 + sl_pct)
    return entry, be, tp, sl

def compute_position_size(balance, stop_pct,
                          risk_frac=RISK_PER_TRADE,
                          min_stake=STAKE_MIN,
                          max_frac=STAKE_MAX_FRAC):
    """
    Деньги в позицию по правилу риск-на-сделку.
    risk_amount = balance * risk_frac
    stake = risk_amount / stop_pct
    Ограничиваем минимумом, максимумом и самим балансом.
    """
    balance = float(max(0.0, balance))
    stop_pct = float(max(1e-6, stop_pct))
    risk_amount = balance * float(risk_frac)
    stake = risk_amount / stop_pct
    stake = max(float(min_stake), min(stake, balance * float(max_frac)))
    stake = min(stake, balance)
    return float(round(stake, 2))

class DartsModelRegistry:
    """
    Хранит единственный DartsPriceModel на символ.
    Исключает постоянные перезагрузки модели с диска.
    """
    def __init__(self):
        self._pool = {}
        self._lock = threading.Lock()

    def get(self, symbol, in_len=AI_INPUT_LEN, out_len=AI_PRED_HORIZON):
        with self._lock:
            m = self._pool.get(symbol)
            if m is None:
                m = DartsPriceModel(symbol)
                # первичная загрузка/создание
                m.load_or_create(in_len, out_len)
                self._pool[symbol] = m
            return m

    def drop(self, symbol):
        with self._lock:
            self._pool.pop(symbol, None)

    def drop_all(self):
        with self._lock:
            self._pool.clear()


# создаём синглтон-реестр
MODEL_REG = DartsModelRegistry()

def trades_path(symbol: str) -> str:
    return os.path.join(TRADES_DIR, f"{symbol.upper()}_trades.json")

def _jsonable_trade(tr: dict) -> dict:
    # делаем сериализуемую копию (фантомы -> list)
    d = dict(tr)
    d["phantoms"] = [list(p) for p in d.get("phantoms", [])]
    return d

def load_trades(symbol: str) -> list:
    p = trades_path(symbol)
    if not os.path.exists(p):
        return []
    try:
        raw = json.load(open(p, "r", encoding="utf-8"))
        out = []
        for t in raw:
            try:
                out.append({
                    "id":           int(t.get("id", 0)),
                    "symbol":       str(t.get("symbol", symbol)),
                    "direction":    str(t.get("direction", "long")),
                    "entry_price":  float(t.get("entry_price", 0.0)),
                    "open_ts":      float(t.get("open_ts", 0.0)),
                    "expected_close_ts": float(t.get("expected_close_ts", 0.0)),
                    "target_pct":   float(t.get("target_pct", 0.0)),
                    "stop_pct":     float(t.get("stop_pct", 0.0)),
                    "max_hold_sec": int(t.get("max_hold_sec", 0)),
                    "stake":        float(t.get("stake", 0.0)),
                    "status":       str(t.get("status", "open")),
                    "exit_price":   (None if t.get("exit_price") is None else float(t.get("exit_price"))),
                    "pnl":          float(t.get("pnl", 0.0)),
                    "forecast":     [float(x) for x in t.get("forecast", [])],
                    "forecast_start_ts": float(t.get("forecast_start_ts", 0.0)),
                    "phantoms":     [tuple(map(float, p)) for p in t.get("phantoms", [])],
                    "best_price":   (None if t.get("best_price") is None else float(t.get("best_price"))),
                    "created_at":   float(t.get("created_at", t.get("open_ts", 0.0))),
                    "close_ts":     (None if t.get("close_ts") is None else float(t.get("close_ts")))
                })
            except Exception:
                continue
        out.sort(key=lambda x: (x.get("open_ts", 0.0), x.get("id", 0)))
        return out[-MAX_TRADES_KEEP:]
    except Exception as e:
        print("Ошибка чтения сделок:", e)
        return []

def save_trades(symbol: str, trades: list) -> None:
    p = trades_path(symbol)
    tmp = p + ".tmp"
    try:
        data = [_jsonable_trade(t) for t in trades[-MAX_TRADES_KEEP:]]
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, p)
    except Exception as e:
        print("Ошибка записи сделок:", e)

def persist_trades_for_symbol(state: dict) -> None:
    with state["lock"]:
        sym = state.get("current_symbol")
        trades = list(state.get("ai_trades", []))
    if sym:
        save_trades(sym, trades)

def next_trade_id_from(trades: list, default_id: int = 1) -> int:
    return (max((int(t.get("id", 0)) for t in trades), default=0) + 1) if trades else default_id


if __name__=="__main__":
    app=CryptoDartsApp(); app.run()
