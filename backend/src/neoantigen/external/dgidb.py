"""DGIdb (Drug-Gene Interaction DB) adapter. Uses v5 GraphQL endpoint."""

from __future__ import annotations

import httpx

from ..models import DrugInteraction

ENDPOINT = "https://dgidb.org/api/graphql"

QUERY = """
query geneDrugs($names: [String!]!) {
  genes(names: $names) {
    nodes {
      name
      interactions {
        drug { name }
        interactionTypes { type }
        sources { sourceDbName }
      }
    }
  }
}
"""


async def search_drugs(client: httpx.AsyncClient, gene: str) -> list[DrugInteraction]:
    try:
        response = await client.post(
            ENDPOINT,
            json={"query": QUERY, "variables": {"names": [gene.upper()]}},
            timeout=15.0,
        )
        response.raise_for_status()
    except httpx.HTTPError:
        return []

    data = response.json().get("data", {})
    nodes = (data.get("genes") or {}).get("nodes") or []
    interactions: list[DrugInteraction] = []
    for node in nodes:
        for inter in node.get("interactions", []):
            drug = (inter.get("drug") or {}).get("name")
            if not drug:
                continue
            types = [t.get("type", "") for t in inter.get("interactionTypes") or []]
            sources = [s.get("sourceDbName", "") for s in inter.get("sources") or []]
            interactions.append(
                DrugInteraction(
                    gene=node.get("name", gene),
                    drug_name=drug,
                    interaction_types=[t for t in types if t],
                    sources=[s for s in sources if s],
                )
            )
    return interactions
