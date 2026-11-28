import { Skeleton } from "../states";

export function MapSkeleton() {
  return (
    <div className="flex flex-col gap-4">
      <Skeleton className="h-[64px] w-full max-w-[720px]" label="Loading the map" />
      <div className="flex flex-wrap gap-4">
        <Skeleton className="aspect-[1000/600] min-w-0 flex-[999_1_720px]" />
        <Skeleton className="h-[480px] flex-[1_1_300px]" />
      </div>
    </div>
  );
}

/** Fills the map box while the first data loads (the map itself is already being drawn). */
export function MapSkeletonFill() {
  return <Skeleton className="h-full w-full rounded-none" label="Loading station data" />;
}
