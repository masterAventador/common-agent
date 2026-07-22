import type { ToolCatalog, ToolGrant, ToolGrantSelection } from "../../api/tools";

export function explicitToolGrantSelection(
  catalog: ToolCatalog,
  grant: ToolGrant,
): ToolGrantSelection {
  const implicit = implicitCapabilityIds(catalog, grant.collection_ids);
  return {
    collection_ids: grant.collection_ids,
    capability_ids: grant.capability_ids.filter((id) => !implicit.has(id)),
  };
}

export function implicitCapabilityIds(
  catalog: ToolCatalog,
  collectionIds: string[],
): Set<string> {
  const selectedSources = new Set(
    catalog.collections
      .filter((collection) => collectionIds.includes(collection.id))
      .flatMap((collection) => collection.source_ids),
  );
  const readySources = new Set(
    catalog.sources
      .filter((source) => source.status === "ready" && selectedSources.has(source.id))
      .map((source) => source.id),
  );
  return new Set(
    catalog.capabilities
      .filter(
        (capability) =>
          capability.status === "active" && readySources.has(capability.source_id),
      )
      .map((capability) => capability.id),
  );
}
