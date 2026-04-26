from api.routes.bc import router as bc_router
from api.routes.brca1 import router as brca1_router
from api.routes.brca2 import router as brca2_router
from api.routes.export import router as export_router
from api.routes.hrd_scars import router as hrd_scars_router
from api.routes.jobs import limiter as jobs_limiter
from api.routes.jobs import router as jobs_router
from api.routes.molecular import router as molecular_router
from api.routes.morphology import router as morphology_router
from api.routes.patients import router as patients_router
from api.routes.radiogenomics import router as radiogenomics_router
from api.routes.screening import router as screening_router
from api.routes.vcf import router as vcf_router

__all__ = [
    "bc_router",
    "brca1_router",
    "brca2_router",
    "export_router",
    "hrd_scars_router",
    "jobs_limiter",
    "jobs_router",
    "molecular_router",
    "morphology_router",
    "patients_router",
    "radiogenomics_router",
    "screening_router",
    "vcf_router",
]
