# L3 of the asset readiness ladder, running inside headless Godot.
#
# Reads a request JSON, loads each resource through ResourceLoader, and writes a
# report JSON. It reports facts and never decides readiness: the Python side
# owns the verdict, so a probe that cannot answer produces an error string
# rather than an optimistic default.
#
# The report goes to a file rather than stdout because Godot writes engine
# banners, import notices, and resource errors to the same streams, and a
# resource that fails to load is exactly the case that floods them.
#
# Invoked as:
#   godot --headless --path <project> --script <this file> --
#         --request <abs path> --report <abs path>
extends SceneTree

# Structural facts a resource may be asked to report for L4. The set is closed:
# an unknown check is an error, never a silent pass. A family skill adds its
# check name here together with the Python structure validator that consumes it.
const KNOWN_CHECKS := ["texture2d", "atlas_texture", "spriteframes", "tileset"]


func _parse_user_args() -> Dictionary:
	var options := {}
	var args := OS.get_cmdline_user_args()
	var index := 0
	while index < args.size():
		var argument: String = args[index]
		if argument.begins_with("--") and index + 1 < args.size():
			options[argument.substr(2)] = args[index + 1]
			index += 2
		else:
			index += 1
	return options


func _structure(resource: Resource, checks: Array) -> Dictionary:
	var structure := {}
	for check in checks:
		if not (check in KNOWN_CHECKS):
			structure[check] = {"error": "unknown structural check: %s" % check}
			continue
		match check:
			"texture2d":
				if resource.is_class("Texture2D"):
					structure[check] = {
						"width": resource.get_width(),
						"height": resource.get_height(),
					}
				else:
					structure[check] = {
						"error": "resource is a %s, not a Texture2D" % resource.get_class(),
					}
			"atlas_texture":
				if resource.is_class("AtlasTexture"):
					var atlas_texture: AtlasTexture = resource
					var atlas_path := ""
					if atlas_texture.atlas != null:
						atlas_path = atlas_texture.atlas.resource_path
					var region := atlas_texture.region
					var margin := atlas_texture.margin
					structure[check] = {
						"has_atlas": atlas_texture.atlas != null,
						"atlas_path": atlas_path,
						"region": [region.position.x, region.position.y, region.size.x, region.size.y],
						"margin": [margin.position.x, margin.position.y, margin.size.x, margin.size.y],
					}
				else:
					structure[check] = {
						"error": "resource is a %s, not an AtlasTexture" % resource.get_class(),
					}
			"tileset":
				if resource.is_class("TileSet"):
					var tile_count := 0
					var alternative_count := 0
					var sources := []
					for source_index in resource.get_source_count():
						var source_id = resource.get_source_id(source_index)
						var source = resource.get_source(source_id)
						if source is TileSetAtlasSource:
							var tiles := []
							for tile_index in source.get_tiles_count():
								var coords = source.get_tile_id(tile_index)
								tile_count += 1
								alternative_count += source.get_alternative_tiles_count(coords) - 1
								var tile_entry = _tile_descriptor(resource, source, coords, 0)
								tile_entry["coords"] = [coords.x, coords.y]
								var alternatives := []
								for alternative_index in source.get_alternative_tiles_count(coords):
									if alternative_index > 0: alternatives.append(_tile_descriptor(resource, source, coords, source.get_alternative_tile_id(coords, alternative_index)))
								var durations := []
								for frame_index in source.get_tile_animation_frames_count(coords): durations.append(source.get_tile_animation_frame_duration(coords, frame_index))
								tile_entry["alternatives"] = alternatives
								tile_entry["animation"] = {"mode": source.get_tile_animation_mode(coords), "columns": source.get_tile_animation_columns(coords), "frames_count": source.get_tile_animation_frames_count(coords), "separation": [source.get_tile_animation_separation(coords).x, source.get_tile_animation_separation(coords).y], "speed": source.get_tile_animation_speed(coords), "frame_durations": durations}
								tiles.append(tile_entry)
							sources.append({"id": source_id, "region_size": [source.texture_region_size.x, source.texture_region_size.y], "margins": [source.margins.x, source.margins.y], "separation": [source.separation.x, source.separation.y], "tiles": tiles})
					structure[check] = {
						"source_count": resource.get_source_count(), "tile_count": tile_count,
						"alternative_count": alternative_count,
						"tile_shape": resource.tile_shape, "sources": sources,
						"tile_size": [resource.tile_size.x, resource.tile_size.y],
						"physics_layers_count": resource.get_physics_layers_count(),
						"navigation_layers_count": resource.get_navigation_layers_count(),
						"occlusion_layers_count": resource.get_occlusion_layers_count(),
						"custom_data_layers_count": resource.get_custom_data_layers_count(),
						"terrain_sets_count": resource.get_terrain_sets_count(),
						"physics_layers": _physics_layers(resource), "navigation_layers": _navigation_layers(resource), "occlusion_layers": _occlusion_layers(resource), "custom_data_layers": _custom_layers(resource), "terrain_sets": _terrain_sets(resource),
					}
				else:
					structure[check] = {"error": "resource is a %s, not a TileSet" % resource.get_class()}
			"spriteframes":
				if resource.is_class("SpriteFrames"):
					var animations := []
					for animation_name in resource.get_animation_names():
						var frame_paths := []
						var frame_durations := []
						var frame_count := resource.get_frame_count(animation_name)
						for frame_index in range(frame_count):
							var texture := resource.get_frame_texture(animation_name, frame_index)
							frame_paths.append(texture.resource_path if texture != null else "")
							frame_durations.append(resource.get_frame_duration(animation_name, frame_index))
						animations.append({
							"name": str(animation_name),
							"fps": resource.get_animation_speed(animation_name),
							"loop": resource.get_animation_loop(animation_name),
							"frame_count": frame_count,
							"frame_paths": frame_paths,
							"frame_durations": frame_durations,
						})
					structure[check] = {"animations": animations}
				else:
					structure[check] = {"error": "resource is a %s, not SpriteFrames" % resource.get_class()}
	return structure

func _tile_descriptor(tile_set: TileSet, source: TileSetAtlasSource, coords: Vector2i, alternative: int) -> Dictionary:
	var data := source.get_tile_data(coords, alternative)
	var peering := []
	for bit in 16: peering.append(data.get_terrain_peering_bit(bit))
	var custom := []
	for layer in tile_set.get_custom_data_layers_count(): custom.append(data.get_custom_data_by_layer_id(layer))
	var collisions := []
	for layer in tile_set.get_physics_layers_count():
		var polygons := []
		for polygon in data.get_collision_polygons_count(layer): polygons.append(_points_json(data.get_collision_polygon_points(layer, polygon)))
		collisions.append(polygons)
	var occlusions := []
	for layer in tile_set.get_occlusion_layers_count():
		var polygons := []
		for polygon in data.get_occluder_polygons_count(layer):
			var item = data.get_occluder_polygon(layer, polygon)
			polygons.append([] if item == null else _points_json(item.polygon))
		occlusions.append(polygons)
	var navigation := []
	for layer in tile_set.get_navigation_layers_count():
		var polygon = data.get_navigation_polygon(layer)
		navigation.append([] if polygon == null else _points_json(polygon.vertices))
	return {"id": alternative, "texture_origin": [data.texture_origin.x, data.texture_origin.y], "z_index": data.z_index, "y_sort_origin": data.y_sort_origin, "probability": data.probability, "terrain_set": data.terrain_set, "terrain": data.terrain, "peering_bits": peering, "custom_data": custom, "collision_polygons": collisions, "occlusion_polygons": occlusions, "navigation_polygons": navigation}

func _points_json(points: PackedVector2Array) -> Array:
	var result := []
	for point in points:
		result.append([point.x, point.y])
	return result

func _physics_layers(tile_set: TileSet) -> Array:
	var result := []
	for index in tile_set.get_physics_layers_count(): result.append({"collision_layer": tile_set.get_physics_layer_collision_layer(index), "collision_mask": tile_set.get_physics_layer_collision_mask(index)})
	return result
func _navigation_layers(tile_set: TileSet) -> Array:
	var result := []
	for index in tile_set.get_navigation_layers_count(): result.append({"layers": tile_set.get_navigation_layer_layers(index)})
	return result
func _occlusion_layers(tile_set: TileSet) -> Array:
	var result := []
	for index in tile_set.get_occlusion_layers_count(): result.append({"light_mask": tile_set.get_occlusion_layer_light_mask(index)})
	return result
func _custom_layers(tile_set: TileSet) -> Array:
	var result := []
	for index in tile_set.get_custom_data_layers_count(): result.append({"name": str(tile_set.get_custom_data_layer_name(index)), "type": tile_set.get_custom_data_layer_type(index)})
	return result
func _terrain_sets(tile_set: TileSet) -> Array:
	var result := []
	for set_index in tile_set.get_terrain_sets_count():
		var terrains := []
		for terrain_index in tile_set.get_terrains_count(set_index):
			var color := tile_set.get_terrain_color(set_index, terrain_index)
			terrains.append({"name": tile_set.get_terrain_name(set_index, terrain_index), "color": [color.r, color.g, color.b, color.a]})
		result.append({"mode": tile_set.get_terrain_set_mode(set_index), "terrains": terrains})
	return result


func _probe(item: Dictionary) -> Dictionary:
	var path: String = item.get("path", "")
	var expected_type: String = item.get("expected_type", "")
	var report := {
		"path": path,
		"expected_type": expected_type,
		"loaded": false,
		"class": "",
		"type_matches": false,
		"structure": {},
		"error": null,
	}
	if path == "" or expected_type == "":
		report["error"] = "request item needs both a path and an expected_type"
		return report
	if not ResourceLoader.exists(path):
		report["error"] = "Godot has no importable resource at %s" % path
		return report
	# CACHE_MODE_IGNORE forces a real load: a cached instance from an earlier
	# probe in the same run would prove nothing about the file on disk.
	var resource := ResourceLoader.load(path, "", ResourceLoader.CACHE_MODE_IGNORE)
	if resource == null:
		report["error"] = "ResourceLoader.load returned null for %s" % path
		return report
	report["loaded"] = true
	report["class"] = resource.get_class()
	# is_class covers the whole inheritance chain, so an imported PNG reporting
	# CompressedTexture2D still matches a declared Texture2D.
	report["type_matches"] = resource.is_class(expected_type)
	report["structure"] = _structure(resource, item.get("checks", []))
	return report


func _fail(message: String, code: int) -> void:
	printerr("asset validation probe: %s" % message)
	quit(code)


func _initialize() -> void:
	var options := _parse_user_args()
	var request_path: String = options.get("request", "")
	var report_path: String = options.get("report", "")
	if request_path == "" or report_path == "":
		_fail("both --request and --report are required", 2)
		return

	var request_file := FileAccess.open(request_path, FileAccess.READ)
	if request_file == null:
		_fail("cannot read request file %s" % request_path, 2)
		return
	var request = JSON.parse_string(request_file.get_as_text())
	request_file.close()
	if typeof(request) != TYPE_DICTIONARY:
		_fail("request file %s is not a JSON object" % request_path, 2)
		return

	var reports := []
	for item in request.get("resources", []):
		if typeof(item) != TYPE_DICTIONARY:
			_fail("every request resource must be a JSON object", 2)
			return
		reports.append(_probe(item))

	var report_file := FileAccess.open(report_path, FileAccess.WRITE)
	if report_file == null:
		_fail("cannot write report file %s" % report_path, 3)
		return
	report_file.store_string(JSON.stringify({
		"godot_version": Engine.get_version_info().get("string", ""),
		"resources": reports,
	}))
	report_file.close()
	quit(0)
