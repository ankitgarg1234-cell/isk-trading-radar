"""Authenticated read-only SEC filing detail endpoint for GEM financial tickets."""
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from gem_data.gem_sec_filing_lookup import lookup_filing, FilingLookupHold

router = APIRouter()


@router.get("/api/gem-portfolio/sec-filing/{cik}")
def sec_filing_details(cik: str):
    try:
        return JSONResponse(lookup_filing(cik),headers={"Cache-Control":"no-store"})
    except FilingLookupHold as exc:
        raise HTTPException(status_code=422,detail="SEC source lookup HOLD: "+str(exc)) from None
