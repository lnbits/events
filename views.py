from fastapi import APIRouter, Depends
from lnbits.core.views.generic import index, index_public  # type: ignore
from lnbits.decorators import check_account_id_exists

events_generic_router = APIRouter()

events_generic_router.add_api_route(
    "/",
    methods=["GET"],
    endpoint=index,
    dependencies=[Depends(check_account_id_exists)],
)

events_generic_router.add_api_route(
    "/{event_id}", methods=["GET"], endpoint=index_public
)

events_generic_router.add_api_route(
    "/ticket/{ticket_id}", methods=["GET"], endpoint=index_public
)

events_generic_router.add_api_route(
    "/register/{event_id}", methods=["GET"], endpoint=index_public
)
