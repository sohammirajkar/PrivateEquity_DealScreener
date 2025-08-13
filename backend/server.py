from fastapi import FastAPI, APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime
import pandas as pd
import numpy as np
import shutil

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Create the main app without a prefix
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# ----------------------------------
# Models
# ----------------------------------
class StatusCheck(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class StatusCheckCreate(BaseModel):
    client_name: str

class DealBase(BaseModel):
    name: str
    sector: str
    subsector: Optional[str] = None
    geography: str
    revenue: float
    ebitda: float
    ebitda_margin: float
    ev: float
    ev_ebitda: Optional[float] = None
    growth_rate: float = 0.0  # as decimal, e.g., 0.1 for 10%
    net_debt: float = 0.0
    deal_stage: str = "sourced"  # sourced, screened, diligence, IC, closed
    source: Optional[str] = None

class DealCreate(DealBase):
    pass

class DealUpdate(BaseModel):
    name: Optional[str] = None
    sector: Optional[str] = None
    subsector: Optional[str] = None
    geography: Optional[str] = None
    revenue: Optional[float] = None
    ebitda: Optional[float] = None
    ebitda_margin: Optional[float] = None
    ev: Optional[float] = None
    ev_ebitda: Optional[float] = None
    growth_rate: Optional[float] = None
    net_debt: Optional[float] = None
    deal_stage: Optional[str] = None
    source: Optional[str] = None

class DealOut(DealBase):
    id: str
    created_at: datetime
    updated_at: datetime
    score: Optional[float] = None

class ScreenerFilters(BaseModel):
    sector: Optional[str] = None
    geography: Optional[str] = None
    ev_ebitda_min: Optional[float] = None
    ev_ebitda_max: Optional[float] = None
    revenue_min: Optional[float] = None
    revenue_max: Optional[float] = None

class LBORequest(BaseModel):
    entry_ebitda: float
    entry_ev_ebitda: float
    revenue_growth: float  # decimal per year
    ebitda_margin: float   # decimal
    capex_pct_of_revenue: float  # decimal
    nwc_pct_change_of_revenue: float  # decimal
    interest_rate: float  # decimal
    leverage_multiple: float  # Debt/EBITDA at entry
    exit_ev_ebitda: float
    years: int = 5
    tax_rate: float = 0.25

class LBOResponse(BaseModel):
    entry_ev: float
    entry_debt: float
    entry_equity: float
    exit_ev: float
    exit_debt: float
    equity_value_at_exit: float
    moic: float
    irr: float
    yearly: List[Dict[str, Any]]

# ----------------------------------
# Utilities
# ----------------------------------

def _now():
    return datetime.utcnow()


def compute_ev_ebitda(ev: float, ebitda: float) -> float:
    if ebitda == 0:
        return 0.0
    return round(ev / ebitda, 2)


def compute_score(d: Dict[str, Any]) -> float:
    # Higher growth and margin, lower multiple wins
    growth = float(d.get('growth_rate', 0) or 0)
    margin = float(d.get('ebitda_margin', 0) or 0)
    mult = float(d.get('ev_ebitda', compute_ev_ebitda(d.get('ev', 0), d.get('ebitda', 0))) or 0)
    # Normalize
    score = 100 * (0.4 * margin + 0.4 * growth + 0.2 * (1.0 / (1.0 + max(mult - 5, 0))))
    return round(score, 2)


def serialize_deal(doc: Dict[str, Any]) -> Dict[str, Any]:
    if not doc:
        return {}
    out = {
        'id': doc.get('_id') or doc.get('id'),
        'name': doc.get('name'),
        'sector': doc.get('sector'),
        'subsector': doc.get('subsector'),
        'geography': doc.get('geography'),
        'revenue': float(doc.get('revenue', 0) or 0),
        'ebitda': float(doc.get('ebitda', 0) or 0),
        'ebitda_margin': float(doc.get('ebitda_margin', 0) or 0),
        'ev': float(doc.get('ev', 0) or 0),
        'ev_ebitda': float(doc.get('ev_ebitda') or compute_ev_ebitda(float(doc.get('ev', 0) or 0), float(doc.get('ebitda', 0) or 0))),
        'growth_rate': float(doc.get('growth_rate', 0) or 0),
        'net_debt': float(doc.get('net_debt', 0) or 0),
        'deal_stage': doc.get('deal_stage', 'sourced'),
        'source': doc.get('source'),
        'created_at': doc.get('created_at'),
        'updated_at': doc.get('updated_at'),
    }
    out['score'] = compute_score(out)
    return out


# ----------------------------------
# Routes
# ----------------------------------
@api_router.get("/")
async def root():
    return {"message": "Hello World"}


@api_router.post("/status", response_model=StatusCheck)
async def create_status_check(input: StatusCheckCreate):
    status_dict = input.dict()
    status_obj = StatusCheck(**status_dict)
    await db.status_checks.insert_one({**status_obj.dict(), "_id": status_obj.id})
    return status_obj


@api_router.get("/status", response_model=List[StatusCheck])
async def get_status_checks():
    status_checks = await db.status_checks.find().to_list(1000)
    # Convert _id->id if present
    normalized = []
    for s in status_checks:
        s['id'] = s.get('_id', s.get('id'))
        s.pop('_id', None)
        normalized.append(StatusCheck(**s))
    return normalized


# Deals CRUD
@api_router.post("/deals", response_model=DealOut)
async def create_deal(payload: DealCreate):
    deal = payload.dict()
    deal_id = str(uuid.uuid4())
    now = _now()
    if not deal.get('ev_ebitda'):
        deal['ev_ebitda'] = compute_ev_ebitda(deal['ev'], deal['ebitda'])
    doc = {**deal, "_id": deal_id, "created_at": now, "updated_at": now}
    await db.deals.insert_one(doc)
    return DealOut(**serialize_deal(doc))


@api_router.get("/deals", response_model=List[DealOut])
async def list_deals(
    sector: Optional[str] = None,
    geography: Optional[str] = None,
    ev_ebitda_min: Optional[float] = None,
    ev_ebitda_max: Optional[float] = None,
    revenue_min: Optional[float] = None,
    revenue_max: Optional[float] = None,
    limit: int = 200
):
    q: Dict[str, Any] = {}
    if sector:
        q['sector'] = sector
    if geography:
        q['geography'] = geography
    # For numeric filters we may need to use ranges. Since ev_ebitda may be null in DB, compute fallback when serializing
    if revenue_min is not None or revenue_max is not None:
        rng = {}
        if revenue_min is not None:
            rng['$gte'] = revenue_min
        if revenue_max is not None:
            rng['$lte'] = revenue_max
        q['revenue'] = rng

    docs = await db.deals.find(q).limit(limit).to_list(length=limit)
    out = [serialize_deal(d) for d in docs]
    # Apply ev/ebitda post-filter if provided
    def within_ev_ebitda(x):
        v = x.get('ev_ebitda') or 0
        if ev_ebitda_min is not None and v < ev_ebitda_min:
            return False
        if ev_ebitda_max is not None and v > ev_ebitda_max:
            return False
        return True
    if ev_ebitda_min is not None or ev_ebitda_max is not None:
        out = [x for x in out if within_ev_ebitda(x)]
    # Sort by score desc
    out.sort(key=lambda x: x.get('score', 0), reverse=True)
    return [DealOut(**x) for x in out]


@api_router.put("/deals/{deal_id}", response_model=DealOut)
async def update_deal(deal_id: str, payload: DealUpdate):
    updates = {k: v for k, v in payload.dict().items() if v is not None}
    if 'ev' in updates or 'ebitda' in updates:
        # recompute multiple if possible
        new_doc = await db.deals.find_one({"_id": deal_id})
        if not new_doc:
            raise HTTPException(status_code=404, detail="Deal not found")
        ev = updates.get('ev', new_doc.get('ev', 0))
        ebitda = updates.get('ebitda', new_doc.get('ebitda', 0))
        updates['ev_ebitda'] = compute_ev_ebitda(ev, ebitda)
    updates['updated_at'] = _now()
    result = await db.deals.find_one_and_update({"_id": deal_id}, {"$set": updates}, return_document=True)
    if result is None:
        raise HTTPException(status_code=404, detail="Deal not found")
    doc = await db.deals.find_one({"_id": deal_id})
    return DealOut(**serialize_deal(doc))


@api_router.delete("/deals/{deal_id}")
async def delete_deal(deal_id: str):
    res = await db.deals.delete_one({"_id": deal_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Deal not found")
    return {"status": "deleted"}


@api_router.post("/deals/screener", response_model=List[DealOut])
async def screener(filters: ScreenerFilters):
    return await list_deals(
        sector=filters.sector,
        geography=filters.geography,
        ev_ebitda_min=filters.ev_ebitda_min,
        ev_ebitda_max=filters.ev_ebitda_max,
        revenue_min=filters.revenue_min,
        revenue_max=filters.revenue_max,
    )


@api_router.get("/deals/metrics")
async def deals_metrics():
    docs = await db.deals.find({}).limit(1000).to_list(1000)
    if not docs:
        return {"count": 0, "avg_multiple": None, "median_multiple": None, "by_sector": {}, "by_geo": {}}
    ser = [serialize_deal(d) for d in docs]
    multiples = [x['ev_ebitda'] for x in ser if x.get('ev_ebitda') and x['ev_ebitda'] > 0]
    avg_mult = round(float(np.mean(multiples)), 2) if multiples else None
    median_mult = round(float(np.median(multiples)), 2) if multiples else None
    by_sector: Dict[str, int] = {}
    by_geo: Dict[str, int] = {}
    for x in ser:
        by_sector[x['sector']] = by_sector.get(x['sector'], 0) + 1
        by_geo[x['geography']] = by_geo.get(x['geography'], 0) + 1
    return {
        "count": len(ser),
        "avg_multiple": avg_mult,
        "median_multiple": median_mult,
        "by_sector": by_sector,
        "by_geo": by_geo,
    }


# LBO quick model
@api_router.post("/lbo/quick", response_model=LBOResponse)
async def lbo_quick(req: LBORequest):
    entry_ev = req.entry_ebitda * req.entry_ev_ebitda
    debt = req.leverage_multiple * req.entry_ebitda
    equity = entry_ev - debt
    if equity <= 0:
        raise HTTPException(status_code=400, detail="Equity must be positive; adjust leverage or entry multiple")

    years = req.years
    margin = req.ebitda_margin
    growth = req.revenue_growth

    # infer starting revenue from EBITDA and margin
    revenue = req.entry_ebitda / max(margin, 1e-6)
    ebitda = req.entry_ebitda

    yearly = []
    for y in range(1, years + 1):
        # grow revenue and infer EBITDA via margin
        revenue = revenue * (1 + growth)
        ebitda = revenue * margin
        interest = debt * req.interest_rate
        capex = revenue * req.capex_pct_of_revenue
        nwc_change = (revenue * req.nwc_pct_change_of_revenue)
        tax = max(ebitda - interest, 0) * req.tax_rate
        fcf = (ebitda - capex - nwc_change - interest - tax)
        # Use all FCF to amortize debt
        debt = max(debt - max(fcf, 0), 0)
        yearly.append({
            "year": y,
            "revenue": round(revenue, 2),
            "ebitda": round(ebitda, 2),
            "interest": round(interest, 2),
            "capex": round(capex, 2),
            "nwc_change": round(nwc_change, 2),
            "tax": round(tax, 2),
            "fcf": round(fcf, 2),
            "debt_end": round(debt, 2),
        })

    exit_ev = ebitda * req.exit_ev_ebitda
    equity_exit = exit_ev - debt
    moic = equity_exit / equity
    irr = (moic ** (1 / years)) - 1

    resp = LBOResponse(
        entry_ev=round(entry_ev, 2),
        entry_debt=round(req.leverage_multiple * req.entry_ebitda, 2),
        entry_equity=round(equity, 2),
        exit_ev=round(exit_ev, 2),
        exit_debt=round(debt, 2),
        equity_value_at_exit=round(equity_exit, 2),
        moic=round(moic, 2),
        irr=round(irr, 4),
        yearly=yearly
    )
    return resp


# Chunked CSV upload flow
UPLOAD_ROOT = Path('/tmp/uploads')
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)


@api_router.post('/upload/init')
async def upload_init():
    upload_id = str(uuid.uuid4())
    (UPLOAD_ROOT / upload_id).mkdir(parents=True, exist_ok=True)
    return {"upload_id": upload_id}


@api_router.post('/upload/chunk')
async def upload_chunk(upload_id: str = Form(...), index: int = Form(...), chunk: UploadFile = File(...)):
    folder = UPLOAD_ROOT / upload_id
    if not folder.exists():
        raise HTTPException(status_code=400, detail="Invalid upload_id")
    dest = folder / f"part_{index:06d}"
    # Save chunk
    with open(dest, 'wb') as f:
        shutil.copyfileobj(chunk.file, f)
    return {"status": "ok", "index": index}


@api_router.post('/upload/complete')
async def upload_complete(upload_id: str = Form(...)):
    folder = UPLOAD_ROOT / upload_id
    if not folder.exists():
        raise HTTPException(status_code=400, detail="Invalid upload_id")
    # Concatenate parts
    parts = sorted(folder.glob('part_*'))
    if not parts:
        raise HTTPException(status_code=400, detail="No parts uploaded")
    assembled = folder / 'assembled.csv'
    with open(assembled, 'wb') as outfile:
        for p in parts:
            with open(p, 'rb') as infile:
                shutil.copyfileobj(infile, outfile)
    # Parse CSV
    try:
        df = pd.read_csv(assembled)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"CSV parse failed: {e}")

    # Expected columns; attempt to map flexibly
    col_map = {}
    lower_cols = {c.lower(): c for c in df.columns}
    def pick(*names):
        for n in names:
            if n in lower_cols:
                return lower_cols[n]
        return None

    col_map['name'] = pick('name', 'company', 'company_name')
    col_map['sector'] = pick('sector')
    col_map['subsector'] = pick('subsector', 'sub_sector')
    col_map['geography'] = pick('geography', 'geo', 'country', 'region')
    col_map['revenue'] = pick('revenue', 'ltm_revenue', 'ntm_revenue')
    col_map['ebitda'] = pick('ebitda', 'ltm_ebitda', 'ntm_ebitda')
    col_map['ev'] = pick('ev', 'enterprise_value')
    col_map['ev_ebitda'] = pick('ev/ebitda', 'ev_ebitda', 'multiple')
    col_map['growth_rate'] = pick('growth', 'growth_rate', 'revenue_growth')
    col_map['net_debt'] = pick('net_debt', 'debt')

    required = ['name', 'sector', 'geography', 'revenue', 'ebitda']
    for r in required:
        if not col_map.get(r):
            raise HTTPException(status_code=400, detail=f"Missing required column in CSV: {r}")

    records = []
    now = _now()
    for _, row in df.iterrows():
        try:
            name = str(row[col_map['name']])
            sector = str(row[col_map['sector']])
            geography = str(row[col_map['geography']])
            revenue = float(row[col_map['revenue']])
            ebitda = float(row[col_map['ebitda']])
            subsector = str(row[col_map['subsector']]) if col_map.get('subsector') else None
            ev = float(row[col_map['ev']]) if col_map.get('ev') else max(ebitda, 0) * 8.0
            ev_ebitda = float(row[col_map['ev_ebitda']]) if col_map.get('ev_ebitda') else compute_ev_ebitda(ev, ebitda)
            growth_rate = float(row[col_map['growth_rate']]) if col_map.get('growth_rate') else 0.0
            net_debt = float(row[col_map['net_debt']]) if col_map.get('net_debt') else 0.0
            ebitda_margin = ebitda / revenue if revenue else 0.0
            rid = str(uuid.uuid4())
            doc = {
                "_id": rid,
                "name": name,
                "sector": sector,
                "subsector": subsector,
                "geography": geography,
                "revenue": revenue,
                "ebitda": ebitda,
                "ebitda_margin": ebitda_margin,
                "ev": ev,
                "ev_ebitda": ev_ebitda,
                "growth_rate": growth_rate,
                "net_debt": net_debt,
                "deal_stage": "sourced",
                "source": "csv_upload",
                "created_at": now,
                "updated_at": now,
            }
            records.append(doc)
        except Exception:
            continue

    if records:
        await db.deals.insert_many(records)
    # Cleanup is optional; keep files for debug
    return {"inserted": len(records)}


# Seed endpoint for quick demo
@api_router.post('/seed')
async def seed_demo():
    sample = [
        {
            "_id": str(uuid.uuid4()),
            "name": "Acme Logistics",
            "sector": "Industrials",
            "subsector": "Logistics",
            "geography": "US",
            "revenue": 250.0,
            "ebitda": 37.5,
            "ebitda_margin": 0.15,
            "ev": 300.0,
            "ev_ebitda": 8.0,
            "growth_rate": 0.08,
            "net_debt": 120.0,
            "deal_stage": "screened",
            "source": "seed",
            "created_at": _now(),
            "updated_at": _now(),
        },
        {
            "_id": str(uuid.uuid4()),
            "name": "CloudHealth SaaS",
            "sector": "Technology",
            "subsector": "SaaS",
            "geography": "US",
            "revenue": 120.0,
            "ebitda": 36.0,
            "ebitda_margin": 0.30,
            "ev": 1080.0,
            "ev_ebitda": 30.0,
            "growth_rate": 0.35,
            "net_debt": 0.0,
            "deal_stage": "sourced",
            "source": "seed",
            "created_at": _now(),
            "updated_at": _now(),
        },
        {
            "_id": str(uuid.uuid4()),
            "name": "Euro Med Devices",
            "sector": "Healthcare",
            "subsector": "MedTech",
            "geography": "EU",
            "revenue": 340.0,
            "ebitda": 68.0,
            "ebitda_margin": 0.20,
            "ev": 748.0,
            "ev_ebitda": 11.0,
            "growth_rate": 0.12,
            "net_debt": 200.0,
            "deal_stage": "diligence",
            "source": "seed",
            "created_at": _now(),
            "updated_at": _now(),
        }
    ]
    await db.deals.insert_many(sample)
    return {"inserted": len(sample)}


# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()