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
const KNOWN_CHECKS := ["texture2d", "tileset"]


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
								var data = source.get_tile_data(coords, 0)
								var durations := []
								for frame_index in source.get_tile_animation_frames_count(coords): durations.append(source.get_tile_animation_frame_duration(coords, frame_index))
								tiles.append({"coords": [coords.x, coords.y], "texture_origin": [data.texture_origin.x, data.texture_origin.y], "z_index": data.z_index, "y_sort_origin": data.y_sort_origin, "probability": data.probability, "terrain_set": data.terrain_set, "terrain": data.terrain, "animation": {"mode": source.get_tile_animation_mode(coords), "columns": source.get_tile_animation_columns(coords), "frames_count": source.get_tile_animation_frames_count(coords), "separation": [source.get_tile_animation_separation(coords).x, source.get_tile_animation_separation(coords).y], "speed": source.get_tile_animation_speed(coords), "frame_durations": durations}})
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
					}
				else:
					structure[check] = {"error": "resource is a %s, not a TileSet" % resource.get_class()}
	return structure


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
