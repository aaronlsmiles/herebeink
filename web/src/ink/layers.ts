// three.js layers: each SparkRenderer generates only the meshes on the camera's layers, so the
// data passes and the shade pass never draw each other's splats (spike S1).
export const LAYER = {
  shade: 0,
  gbuf: 1,
  flag: 2,
  /** Drawn only in the map view (the map's coastline). */
  map: 3,
  /** Drawn only in the walk view (the floor coastline). */
  walk: 4,
} as const;
