extends SceneTree

func _args() -> Dictionary:
	var result := {}
	var args := OS.get_cmdline_user_args()
	var index := 0
	while index + 1 < args.size():
		if args[index].begins_with("--"):
			result[args[index].substr(2)] = args[index + 1]
		index += 2
	return result

func _v2(value: Array) -> Vector2i:
	return Vector2i(int(value[0]), int(value[1]))

func _points(values: Array) -> PackedVector2Array:
	var result := PackedVector2Array()
	for value in values:
		result.append(Vector2(float(value[0]), float(value[1])))
	return result

func _shape(value: Variant) -> int:
	if value is int:
		return value
	return {"square": TileSet.TILE_SHAPE_SQUARE, "isometric": TileSet.TILE_SHAPE_ISOMETRIC,
		"half_offset_square": TileSet.TILE_SHAPE_HALF_OFFSET_SQUARE,
		"hexagon": TileSet.TILE_SHAPE_HEXAGON}.get(str(value), TileSet.TILE_SHAPE_SQUARE)

func _layers(tile_set: TileSet, recipe: Dictionary) -> void:
	for layer in recipe.get("physics_layers", []):
		tile_set.add_physics_layer()
		var i := tile_set.get_physics_layers_count() - 1
		tile_set.set_physics_layer_collision_layer(i, int(layer.get("collision_layer", 1)))
		tile_set.set_physics_layer_collision_mask(i, int(layer.get("collision_mask", 1)))
	for layer in recipe.get("navigation_layers", []):
		tile_set.add_navigation_layer()
		var i := tile_set.get_navigation_layers_count() - 1
		tile_set.set_navigation_layer_layers(i, int(layer.get("layers", 1)))
	for layer in recipe.get("occlusion_layers", []):
		tile_set.add_occlusion_layer()
		var i := tile_set.get_occlusion_layers_count() - 1
		tile_set.set_occlusion_layer_light_mask(i, int(layer.get("light_mask", 1)))
	for layer in recipe.get("custom_data_layers", []):
		tile_set.add_custom_data_layer()
		var i := tile_set.get_custom_data_layers_count() - 1
		tile_set.set_custom_data_layer_name(i, StringName(layer.get("name", "")))
		tile_set.set_custom_data_layer_type(i, int(layer.get("type", TYPE_NIL)))
	for set_recipe in recipe.get("terrain_sets", []):
		tile_set.add_terrain_set()
		var terrain_set := tile_set.get_terrain_sets_count() - 1
		tile_set.set_terrain_set_mode(terrain_set, int(set_recipe.get("mode", TileSet.TERRAIN_MODE_MATCH_CORNERS_AND_SIDES)))
		for terrain_recipe in set_recipe.get("terrains", []):
			tile_set.add_terrain(terrain_set)
			var terrain := tile_set.get_terrains_count(terrain_set) - 1
			tile_set.set_terrain_name(terrain_set, terrain, String(terrain_recipe.get("name", "")))
			if terrain_recipe.has("color"): tile_set.set_terrain_color(terrain_set, terrain, Color(terrain_recipe["color"]))

func _tile_data(source: TileSetAtlasSource, coords: Vector2i, alternative: int, tile: Dictionary) -> void:
	var data := source.get_tile_data(coords, alternative)
	data.texture_origin = _v2(tile.get("texture_origin", [0, 0]))
	data.z_index = int(tile.get("z_index", 0))
	data.y_sort_origin = int(tile.get("y_sort_origin", 0))
	data.probability = float(tile.get("probability", 1.0))
	if tile.has("terrain_set"): data.terrain_set = int(tile["terrain_set"])
	if tile.has("terrain"): data.terrain = int(tile["terrain"])
	for bit in tile.get("peering_bits", []):
		data.set_terrain_peering_bit(int(bit["bit"]), int(bit["terrain"]))
	for custom in tile.get("custom_data", []): data.set_custom_data_by_layer_id(int(custom["layer"]), custom.get("value"))
	for collision in tile.get("collision_polygons", []):
		var layer := int(collision["layer"])
		var count := data.get_collision_polygons_count(layer)
		data.set_collision_polygons_count(layer, count + 1)
		data.set_collision_polygon_points(layer, count, _points(collision["points"]))
	for occluder in tile.get("occlusion_polygons", []):
		var layer := int(occluder["layer"])
		var count := data.get_occluder_polygons_count(layer)
		data.set_occluder_polygons_count(layer, count + 1)
		var polygon := OccluderPolygon2D.new(); polygon.polygon = _points(occluder["points"])
		data.set_occluder_polygon(layer, count, polygon)
	for navigation in tile.get("navigation_polygons", []):
		var layer := int(navigation["layer"])
		var polygon := NavigationPolygon.new(); polygon.add_outline(_points(navigation["points"])); polygon.make_polygons_from_outlines()
		data.set_navigation_polygon(layer, polygon)

func _source(tile_set: TileSet, item: Dictionary, fallback_id: int) -> void:
	var source := TileSetAtlasSource.new()
	source.texture = load(item["texture"])
	if source.texture == null: push_error("cannot load atlas texture " + item["texture"]); quit(2); return
	source.texture_region_size = _v2(item.get("region_size", item.get("tile_size", [16, 16])))
	source.margins = _v2(item.get("margins", [0, 0]))
	source.separation = _v2(item.get("separation", [0, 0]))
	for tile in item["tiles"]:
		var coords := _v2(tile["coords"])
		source.create_tile(coords)
		_tile_data(source, coords, 0, tile)
		for alternative in tile.get("alternatives", []):
			var id := int(alternative["id"])
			source.create_alternative_tile(coords, id)
			_tile_data(source, coords, id, alternative)
		var animation: Dictionary = tile.get("animation", {})
		if not animation.is_empty():
			source.set_tile_animation_columns(coords, int(animation.get("columns", 1)))
			source.set_tile_animation_frames_count(coords, int(animation.get("frames_count", 1)))
			source.set_tile_animation_separation(coords, _v2(animation.get("separation", [0, 0])))
			source.set_tile_animation_speed(coords, float(animation.get("speed", 1.0)))
			for frame in animation.get("frame_durations", []): source.set_tile_animation_frame_duration(coords, int(frame["frame"]), float(frame["duration"]))
	tile_set.add_source(source, int(item.get("id", fallback_id)))

func _initialize() -> void:
	var args := _args(); var file := FileAccess.open(args.get("recipe", ""), FileAccess.READ)
	if file == null: push_error("cannot read TileSet recipe"); quit(2); return
	var recipe = JSON.parse_string(file.get_as_text()); file.close()
	if typeof(recipe) != TYPE_DICTIONARY: push_error("TileSet recipe must be an object"); quit(2); return
	var tile_set := TileSet.new(); tile_set.tile_shape = _shape(recipe.get("tile_shape", "square")); tile_set.tile_size = _v2(recipe["tile_size"])
	_layers(tile_set, recipe)
	for index in recipe["sources"].size(): _source(tile_set, recipe["sources"][index], index)
	var error := ResourceSaver.save(tile_set, args.get("output", ""))
	if error != OK: push_error("ResourceSaver.save failed: " + str(error)); quit(error); return
	quit()
