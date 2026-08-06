# 浠ｇ爜搴撴寚鍗?
鏈〉闈㈠ GodotMaker 浠撳簱閫愮洰褰曡繘琛屾繁搴︿粙缁嶏紝甯姪浣犲湪寮€濮嬩慨鏀逛箣鍓嶅缓绔嬪叏灞€璁ょ煡銆傚闇€绠€鐭瑙堬紝璇峰弬闃?[寮€鍙戠幆澧冩惌寤篯(development-setup.md)銆傛兂浜嗚В鍚勬ā鍧楀湪杩愯鏃跺浣曞崗浣滐紝璇风户缁槄璇绘湰鏂囥€?
## 浠撳簱鐩綍缁撴瀯

```
GodotMaker/
鈹溾攢鈹€ hooks/                   8 涓?hook 鑴氭湰 + hooks/metrics/ 瀛愮郴缁?鈹溾攢鈹€ agents/                  瀛?Agent 瀹氫箟锛坵orker銆乿erifier銆乺eviewer銆乤nalyst銆乤sset-producer銆乬dd-auditor锛?鈹溾攢鈹€ skills/
鈹?  鈹溾攢鈹€ core/                瑙掕壊鎶€鑳?+ 杈呭姪鎶€鑳?+ _shared/
鈹?  鈹斺攢鈹€ reviewer/            8 涓鏌ユ妧鑳斤紙鍚勫惈 gotchas.md + checklist.md锛?鈹溾攢鈹€ tools/                   publish.py, check_env.py, check_project.py, asset_*.py, migrate.py
鈹溾攢鈹€ config/                  config.yaml.default, stage_schemas.json, addon_versions.json
鈹溾攢鈹€ agent-runtimes/          runner 涓撳睘 reference銆乼emplate銆乭ook config 鍜?plugin adapter
鈹溾攢鈹€ templates/               鏂囨。妯℃澘锛圙DD, PLAN, STRUCTURE, SCENES, ASSETS, GAP, MEMORY, TOC锛?鈹溾攢鈹€ tests/                   ~320 涓?hook 鍜屽伐鍏风殑鍗曞厓娴嬭瘯
鈹溾攢鈹€ docs/                    versioning.md, hooks.md, wiki/, update/, contributing/, reference/
鈹溾攢鈹€ shell/                   publish.sh / publish.ps1, report.sh / report.bat
鈹溾攢鈹€ migrations/              璺ㄧ増鏈縼绉昏剼鏈?鈹溾攢鈹€ VERSION                  璇箟鐗堟湰鍙风殑鍞竴鐪熷疄鏉ユ簮
鈹斺攢鈹€ CHANGELOG.md             姣忔鍙戠増鐨勫彉鏇磋鏄?```

---

## hooks/

鍏釜 Python 鑴氭湰锛岃礋璐ｅ己鍒舵墽琛屾祦姘寸嚎瑙勫垯銆傛瘡涓剼鏈粠 `sys.stdin` 璇诲彇 JSON payload锛屽喅瀹氭槸鍚﹀厑璁告垨鎷︽埅璇ユ搷浣滐紝鐒跺悗灏?JSON 鍝嶅簲鍐欏叆 stdout锛堥潤榛樻斁琛屾椂鐩存帴 exit 0锛屼笉杈撳嚭浠讳綍鍐呭锛夈€?
鍚勮剼鏈強鍏跺鐞嗙殑浜嬩欢锛?
| 鑴氭湰 | 浜嬩欢 | 鏄惁鎷︽埅 |
|--------|-------|---------|
| `session_start.py` | SessionStart | 鍚?|
| `check_file_permissions.py` | PreToolUse (Write\|Edit) | 鏄?|
| `stage_reminder.py` | PreToolUse (Write\|Edit) | 鏄?|
| `check_stage_prerequisites.py` | PreToolUse (Agent) | 鏄?|
| `check_asset_access.py` | PreToolUse (Read) | 鏄?|
| `log_subagent.py` | SubagentStart | 鍚?|
| `on_subagent_stop.py` | SubagentStop | 濮旀墭鎵ц |
| `check_worker_report.py` | 鐢?on_subagent_stop.py 璋冪敤 | 鏄?|
| `check_completion.py` | Stop | 鏄?|

Hook 娉ㄥ唽鍏崇郴锛堝摢涓剼鏈搷搴斿摢涓簨浠讹級鎸?runner 鍖哄垎銆侰laude Code 鍜?Codex 浣跨敤 `agent-runtimes/<agent>/config/` 涓嬬殑閰嶇疆鏂囦欢锛汷penCode 浣跨敤
`agent-runtimes/opencode/plugins/godotmaker-hooks.js` 浣滀负 plugin adapter銆?
### hooks/metrics/

涓€涓敤浜庤褰曚細璇濇湡闂村彂鐢熶簨浠剁殑灏忓瀷瀛愮郴缁熴€侶ook 閫氳繃璋冪敤 `record_event()` 灏?JSON 琛岃拷鍔犲埌 `.godotmaker/metrics_current.jsonl`锛堝綋鍓嶄細璇濓級鍜?`.godotmaker/metrics_total.jsonl`锛堝叏閲忕敓鍛藉懆鏈熸棩蹇楋級銆俙state.py` 妯″潡璐熻矗鍦?`.godotmaker/state.json` 涓鐞嗗彲鍙樼殑浼氳瘽鍐呰鏁板櫒锛堟嫤鎴鏁扮瓑锛夈€俙session_start.py` 鍦ㄦ瘡娆℃柊浼氳瘽寮€濮嬫椂閲嶇疆涓よ€呫€?
鍏充簬缂栧啓 hook 鍜屼娇鐢?metrics API 鐨勮缁嗚鏄庯紝璇峰弬闃?[缂栧啓 Hook](writing-a-hook.md)銆?
### 鏉冮檺濂戠害鐨勪笁灞傚垝鍒?
瑙掕壊鏉冮檺鍒嗗竷鍦ㄤ笁澶勶紝鍒绘剰鏈夐噸鍙狅紝浣嗘瘡涓€灞傝亴璐ｄ笉鍚?鈥?鏀瑰姩鍏朵腑涓€灞傛椂锛岃妫€鏌ュ叾浠栧眰鏄惁瑕佽窡鐫€鍔細

| 灞?| 鎺у埗浠€涔?| 鐪熷€兼潵婧?|
|----|---------|---------|
| `config/stage_schemas.json` | 瑙掕壊瀹屾垚浜嗘病锛熶笅涓€涓鑹插惎鍔ㄥ墠蹇呴』瀛樺湪鐨勪骇鍑烘枃浠舵竻鍗曘€?| 鐢?`stage_reminder.py`锛堝畬鎴愭牎楠岋級鍜?`check_stage_prerequisites.py`锛坵orker 娲惧彂鍓嶇疆妫€鏌ワ級璇诲彇銆?|
| `hooks/check_file_permissions.py` | 褰撳墠瑙掕壊鐜板湪鑳藉啓浠€涔堬紵姣忔 Write/Edit 宸ュ叿璋冪敤閮藉己鍒舵墽琛岀殑 per-role 鍐欐潈闄愮櫧鍚嶅崟銆?| 杩愯鏃舵潈闄愮殑鏈€缁堝垽瀹氾紱schema 涓嶅畾涔夊啓鏉冮檺銆?|
| `skills/core/gm-*/SKILL.md` 鐨?"Permission" 娈佃惤 | 缁欒瑙掕壊鐨勬墽琛岃€呰鐨勪汉绫荤増闀滃儚銆?| 搴斿綋涓?hook 涓€鑷达紱鑻ユ紓绉伙紝杩愯鏃朵互 hook 涓哄噯 鈥?浣嗚 SKILL 鐨勮础鐚€呬細琚瀵笺€?|

涓€涓父瑙佽瑙ｆ槸鎶?`stage_schemas.json` 褰撴垚瀹屾暣鐨勫啓鏉冮檺濂戠害銆傚畠**涓嶆槸** 鈥?瀹冨彧鍒楀嚭瀹屾垚鏍￠獙鎵€闇€鐨勪骇鍑烘枃浠躲€傜粰鏌愪釜瑙掕壊鐨?schema 鍔犳枃浠?*涓嶄細**鑷姩鑾峰緱鍐欐潈闄愶紝杩樺緱鍚屾椂鎵╁睍 hook 鐨勭櫧鍚嶅崟銆?
---

## agents/

瀛?Agent 瀹氫箟鏂囦欢锛屾瘡涓?Agent 瀵瑰簲涓€涓?Markdown 鏂囦欢銆傛瘡涓枃浠堕兘甯︽湁 YAML front-matter锛坄name`銆乣description`銆乣model`锛夊拰绯荤粺 prompt 姝ｆ枃銆俙publish.py` 浼氬皢瀹冧滑閮ㄧ讲鍒?`<target>/.claude/agents/`锛孋laude Code 閫氳繃 `subagent_type` 璇嗗埆璋冪敤銆?
| Agent | 鑱岃矗 | 鐢辫皝娲惧彂 |
|-------|------|----------|
| `worker.md` | 绔埌绔疄鐜颁竴涓换鍔★紙浠ｇ爜 + 鍗曞厓娴嬭瘯锛?| `/gm-build`銆乣/gm-fixgap` |
| `verifier.md` | 瀵?Worker 鐨勪骇鍑鸿繘琛屾満姊版牎楠岋紙鏋勫缓銆佹祴璇曘€佹枃浠跺瓨鍦ㄦ€э級 | `/gm-build`銆乣/gm-fixgap` |
| `reviewer.md` | 瀵圭収 `skills/reviewer/<domain>` 鐨?checklist 瀹℃煡浠ｇ爜骞舵姤鍛婇棶棰?| `/gm-build`銆乣/gm-fixgap` |
| `analyst.md` | 鍒嗘瀽鐢ㄦ埛鎻愪緵鐨勮祫婧愬苟杈撳嚭 manifest | `/gm-asset` |
| `asset-producer.md` | 鐢熸垚涓€涓瑙夎祫婧愮敓浜у崟鍏?| `/gm-asset` |
| `gdd-auditor.md` | 鐙珛瀹¤ GDD 鑽夌锛屽鐓?9 绫?checklist 姣忚疆杩斿洖 5鈥? 涓ˉ闂?| `game-planner`锛圧ounds 6 + 7锛?|

娲惧彂鍗忚锛堣皟鐢ㄦ牸寮忓拰 brief 妯℃澘锛変綅浜?`skills/core/_shared/{worker,verifier,reviewer,analyst}-dispatch.md` 鎴栨墍灞炶鑹叉妧鑳藉唴銆俙gdd-auditor` 鐩存帴鐢?`skills/core/game-planner/SKILL.md` 鍐呰仈璋冪敤銆?
### 涓よ疆 GDD 瀹¤

`gdd-auditor` 鏄敮涓€涓€涓淳鍙戝崗璁?*涓?*鏀惧湪 `_shared/` 閲岀殑瀛?Agent銆傚畠鍙湪 `game-planner` 鐨?Round 6 + Round 7 璋冪敤锛屾淳鍙戦€昏緫绂诲紑閭ｆ璁胯皥鑴氭湰灏辨病鎰忎箟銆傛妸瀹冩彁鍒?`_shared/` 鍙細澧炲姞璺宠浆锛屼笉浼氬甫鏉ュ鐢ㄣ€?
涓よ疆锛屽叏閮ㄥ湪鏂颁笂涓嬫枃涓窇锛屼娇鐢ㄥ悓涓€涓?`subagent_type`锛?
| 杞 | Round | 杈撳叆 | 杈撳嚭 | 杩欎竴杞瓨鍦ㄧ殑鐞嗙敱 |
|------|-------|------|------|------------------|
| 1 | Round 6 | GDD v1 + 绌虹殑 `Previously Asked` | 5鈥? 涓ˉ闂?| 鎹曟崏 planner 鍦ㄨ璋堜腑閬楁紡鐨勭己鍙?|
| 2 | Round 7 | GDD v2 + Round 6 鐨?*瀹屾暣鍘熸枃**闂鍒楄〃锛堝～鍏?`Previously Asked`锛?| 5鈥? 涓?*鏂?*闂 | 寮鸿揩 auditor 鐪嬩簩绾х己鍙ｈ€屼笉鏄噸澶嶈嚜宸?|

Round 7 brief 涓殑 `Previously Asked` 瀛楁鏄繀濉」锛屼笉鏄彲閫夐」銆備笉濉氨绛変簬璁?auditor 鍦ㄦ柊涓婁笅鏂囬噷瀹屽叏娌℃湁 pass 1 鐨勮蹇嗭紝缁撴灉浼氶噸澶嶅悓鏍风殑闂銆佺櫧鐧芥氮璐逛竴杞€俙game-planner` SKILL.md 鐢?`**You MUST populate**` 鏍囪杩欎釜瀛楁锛宍gdd-auditor.md` 涔熸妸"鍦?`Previously Asked` 涓噸澶嶉棶棰?鍒椾负纭€х姝⑩€斺€斾袱灞備竴璧峰己鍒跺悓涓€浠藉绾︺€?
`auditor_model` 榛樿鍊兼槸 `sonnet`锛堝湪 `config/config.yaml.default` 涓厤缃級锛涘璁′换鍔℃槸 checklist 椹卞姩鐨勶紝涓嶉渶瑕?opus 绾ф帹鐞嗐€?
---

## skills/core/

瑙掕壊鎶€鑳藉拰杈呭姪鎶€鑳斤紝姣忎釜鎶€鑳藉搴斾竴涓洰褰曘€傛瘡涓洰褰曡嚦灏戝寘鍚竴涓甫鏈?YAML front-matter 鍜?prompt 姝ｆ枃鐨?`SKILL.md`銆?
**瑙掕壊鎶€鑳斤紙9 涓級锛?* `gm-scaffold`銆乣gm-gdd`銆乣gm-asset`銆乣gm-build`銆乣gm-verify`銆乣gm-evaluate`銆乣gm-fixgap`銆乣gm-accept`銆乣gm-finalize`銆傝繖浜涙妧鑳戒笌 `/gm-*` 鏂滄潬鍛戒护涓€涓€瀵瑰簲銆傛瘡涓鑹叉妧鑳界殑绗竴涓姩浣滄槸灏嗚鑹插悕鍐欏叆 `.godotmaker/current_role`锛岃繖姝ｆ槸 `check_file_permissions.py` 鐢ㄦ潵鎵ц鍐欏叆瑙勫垯鐨勪緷鎹€?
**杈呭姪鎶€鑳斤紙11 涓級锛?* `game-planner`銆乣project-scaffold`銆乣godot-api`銆乣gecs`銆乣input-mapper`銆乣headless-build`銆乣gdunit-driver`銆乣godot-e2e`銆乣visual-qa`銆乣screenshot`銆乣mcp-driver`銆傝繖浜涙槸鐢辫鑹叉妧鑳藉姞杞界殑鍙傝€冩枃妗ｏ紝鐢ㄦ埛涓嶄細鐩存帴璋冪敤瀹冧滑銆?
### skills/core/_shared/

浠讳綍琚秴杩囦竴涓妧鑳戒娇鐢ㄧ殑鍙傝€冩枃妗ｏ紝閮戒互姝ゅ涓哄敮涓€鐪熷疄鏉ユ簮淇濆瓨銆備緥濡傦細`worker-dispatch.md`銆乣verifier-dispatch.md`銆乣reviewer-dispatch.md`銆乣analyst-dispatch.md`銆?
鍙戝竷鏃讹紝`publish_shared_refs()` 璇诲彇 `_shared/manifest.json`锛屽皢姣忎釜婧愭枃浠跺啓鍏ユ墍鏈夊垪鍑虹殑娑堣垂鎶€鑳界殑 `references/` 鏂囦欢澶广€傝閮ㄧ讲鐨勫壇鏈甫鏈?`<!-- AUTO-GENERATED -->` 澶撮儴锛屾瘡娆″彂甯冮兘浼氳瑕嗙洊銆?
**缂栬緫瑙勫垯锛?*
- 鍙紪杈?`_shared/<file>.md` 涓嬬殑婧愭枃浠讹紝姘歌繙涓嶈缂栬緫宸查儴缃茬殑鍓湰銆?- 鍦ㄦ秷璐规妧鑳界殑 `SKILL.md` 涓紝閫氳繃 `references/<file>.md` 寮曠敤璇ユ枃妗ｏ紙杩欐槸閮ㄧ讲鍚庣殑璺緞锛宍_shared/` 鍦ㄥ凡鍙戝竷椤圭洰涓苟涓嶅瓨鍦級銆?- 鏂板鎴栦慨鏀瑰叡浜枃妗ｅ悗锛岃繍琛?`python -m pytest tests/tools/test_publish_shared.py -q` 纭 manifest 涓庢墍鏈夋秷璐硅€呭紩鐢ㄤ繚鎸佷竴鑷淬€?
manifest 鐨?schema銆佹坊鍔?绉婚櫎娴佺▼鍜岃皟璇曟妧宸ц `docs/contributing/shared-refs.md`銆?
---

## skills/reviewer/

鍏釜瀹℃煡鎶€鑳斤紝姣忎釜棰嗗煙涓€涓細`physics`銆乣animation`銆乣ui`銆乣tilemap`銆乣navigation`銆乣shader`銆乣audio`銆乣particles`銆?
姣忎釜瀹℃煡鎶€鑳界洰褰曞寘鍚伆濂戒笁涓枃浠讹細
- `SKILL.md` 鈥?瀹℃煡鍛?prompt
- `gotchas.md` 鈥?棰嗗煙鐗瑰畾闄烽槺鐩綍锛圠LM 瀹规槗鐘敊鐨勫湴鏂癸級
- `checklist.md` 鈥?涓?gotcha ID 瀵瑰簲鐨勭郴缁熸€ф鏌ラ」

瀹℃煡瀛?Agent锛堢敱 `gm-build` 鍜?`gm-fixgap` 鍒嗗彂锛夋牴鎹?worker 杈撳嚭涓嚭鐜扮殑 Godot 绫诲拰 API 鍔ㄦ€佽鍙栬繖浜涙枃浠讹紝骞朵笉瀛樺湪闈欐€佸垎鍙戝垪琛ㄢ€斺€斿鏌ュ憳鑷鎸戦€夌浉鍏崇殑棰嗗煙鏂囦欢銆傚叧浜庡鏌ユ妧鑳界粨鏋勭殑璇︾粏璇存槑锛岃 [缂栧啓鎶€鑳絔(writing-a-skill.md)銆?
---

## tools/

璐＄尞鑰呭拰鐢ㄦ埛鐩存帴杩愯鐨?Python CLI 鑴氭湰銆?
| 宸ュ叿 | 鐢ㄩ€?|
|------|---------|
| `publish.py` | 灏?GodotMaker 閮ㄧ讲鍒扮洰鏍?Godot 椤圭洰 |
| `check_env.py` | 楠岃瘉 Godot銆丳ython 鍜?API key 鏄惁姝ｇ‘閰嶇疆 |
| `check_project.py` | 妫€楠屽凡鐢熸垚椤圭洰涓殑缂哄け鏂囦欢鍜屾崯鍧忚矾寰?|
| `asset_source_generate.py` | 鏍规嵁 `/gm-asset` spec 鐢熸垚 API 鍚庣 source 鍥剧墖 |
| `asset_layout_guide.py` | 涓哄浐瀹氱綉鏍?source 鍥剧墖鍒涘缓 layout guide |
| `asset_action_process.py` | 灏嗚鑹插姩浣?sheet 澶勭悊鎴愯鑼冨寲 frames 鍜?metadata |
| `asset_sheet_process.py` | 灏嗙敓浜у舰鎬佺殑 2D source sheet 鎷嗘垚 curation candidate |
| `asset_curation_select.py` | 灏嗛€変腑鐨?curation candidate finalize 鍒拌繍琛屾椂绱犳潗璺緞 |
| `migrate.py` | 鍦ㄤ换浣曢潪 MAJOR 鍗囩骇鏃舵妸鏈簲鐢ㄧ殑杩佺Щ鑴氭湰搴旂敤鍒扮洰鏍囬」鐩紱涔熼€氳繃 `--new <slug>` 鐢熸垚鏂拌剼鏈ā鏉?|

### publish.py 濡備綍涓茶仈涓€鍒?
杩愯 `python tools/publish.py <target>` 鏃讹細

1. 浠庝粨搴撴牴鐩綍璇诲彇 `VERSION`锛屼笌 `<target>/.godotmaker/version` 姣旇緝銆侻INOR / MAJOR 鍗囩骇鏃跺脊鍑烘彁绀烘垨鐩存帴鎷︽埅銆?2. 鎵佸钩澶嶅埗 first-class 鎶€鑳斤細`skills/core/`銆乣skills/reviewer/` 鍜?`skills/assets/` 涓嬬殑姣忎釜闈炵鏈夌洰褰曢兘浼氬啓鍏ユ墍閫?agent 鐨勬妧鑳界洰褰曪紙Claude Code 涓?`<target>/.claude/skills/`锛孋odex 涓?`<target>/.agents/skills/`锛夈€俙skills/core/_shared/` 鏂囨。鐢?`publish_shared_refs()` 閮ㄧ讲鍒版秷璐规妧鑳界殑 `references/` 鏂囦欢澶癸紱`skills/assets/_shared/` 涓嶆槸鍙皟鐢ㄧ殑 Skill锛岃€屾槸杩炲悓鍏变韩 schema銆乧ompiler 鍜?L0-L4 validator 涓€璧峰鍒跺埌 `<target>/.godotmaker/asset-runtime/`銆?3. 澶嶅埗 hooks 鈫?`<target>/.godotmaker/hooks/`銆?4. 澶嶅埗 tools 鈫?`<target>/tools/`銆?5. 澶嶅埗 templates 鍒版墍閫?agent 鐨勬ā鏉跨洰褰曘€?6. 澶嶅埗 `config/stage_schemas.json` 鈫?`<target>/.godotmaker/stage_schemas.json`銆?7. 棣栨瀹夎锛堟垨浣跨敤 `--force`锛夋椂锛氬啓鍏ュ搴?agent 鐨勯」鐩寚浠ゆ枃浠讹紙`CLAUDE.md` 鎴?`AGENTS.md`锛夛紝鎻愮ず閰嶇疆 `godotmaker.yaml`锛屽苟鍐欏叆鎵€閫?runner 鐨?hook config 鎴?plugin adapter銆?8. 灏嗗綋鍓嶇増鏈彿鍐欏叆 `<target>/.godotmaker/version`銆?
---

## config/

| 鏂囦欢 | 鎺у埗鍐呭 |
|------|-----------------|
| `settings.json` | Hook 娉ㄥ唽锛氬摢浜涜剼鏈搷搴斿摢浜?Claude Code 浜嬩欢 |
| `stage_schemas.json` | 姣忎釜瑙掕壊鐨勫繀瑕佽緭鍑哄拰绋嬪簭鍖栨鏌ワ紙key 涓鸿鑹插悕锛?|
| `addon_versions.json` | 鎸夊紩鎿庣増鏈攣瀹氱殑 Godot 鎻掍欢鐗堟湰 |

`stage_schemas.json` 鏄?`stage_reminder.py` 鍜?`check_stage_prerequisites.py` 閮戒細璇诲彇鐨?schema銆傚叾 key 涓鸿鑹插悕锛坄scaffold`銆乣gdd`銆乣build` 绛夛級锛屾瘡涓€煎寘鍚彲閫夌殑 `files` 鏁扮粍锛堝繀椤诲瓨鍦ㄤ簬纾佺洏涓婄殑璺緞锛夊拰鍙€夌殑 `checks` 鏁扮粍锛堢▼搴忓寲楠岃瘉鍣ㄥ悕绉帮級銆傚畬鏁?schema 璇存槑瑙?[缂栧啓鎶€鑳絔(writing-a-skill.md)銆?
---

## templates/

Markdown 鏂囨。妯℃澘锛岀敱 `publish.py` 閮ㄧ讲鍒版柊娓告垙椤圭洰鐨勬墍閫?agent 妯℃澘鐩綍涓嬨€傝鑹叉妧鑳藉湪宸ヤ綔杩囩▼涓～鍏呰繖浜涙ā鏉裤€傛ā鏉垮寘鎷細`GDD.md`銆乣PLAN.md`銆乣STRUCTURE.md`銆乣SCENES.md`銆乣ASSETS.md`銆乣GAP.md`銆乣MEMORY.md`銆乣TOC.md`銆乣game-claude.md`銆?
---

## tests/

娴嬭瘯濂椾欢锛屾寜瑕嗙洊瀵硅薄缁勭粐銆?
```
tests/
鈹溾攢鈹€ hooks/
鈹?  鈹溾攢鈹€ helpers.py                       鍏变韩宸ュ叿鍑芥暟锛歳un_hook, is_blocked, write_completed_roles, ...
鈹?  鈹溾攢鈹€ test_check_completion.py
鈹?  鈹溾攢鈹€ test_check_file_permissions.py
鈹?  鈹溾攢鈹€ test_check_stage_prerequisites.py
鈹?  鈹溾攢鈹€ test_check_worker_report.py
鈹?  鈹溾攢鈹€ test_metrics.py
鈹?  鈹溾攢鈹€ test_session_start.py
鈹?  鈹斺攢鈹€ test_stage_reminder.py
鈹溾攢鈹€ tools/
鈹?  鈹溾攢鈹€ conftest.py
鈹?  鈹溾攢鈹€ test_addon_versions.py
鈹?  鈹溾攢鈹€ test_check_classname.py
鈹?  鈹溾攢鈹€ test_check_env.py
鈹?  鈹溾攢鈹€ test_check_project.py
鈹?  鈹溾攢鈹€ test_migrate.py
鈹?  鈹溾攢鈹€ test_publish.py
鈹?  鈹斺攢鈹€ test_publish_shared.py
鈹斺攢鈹€ test_pipeline_e2e.py                 绔埌绔祦姘寸嚎鍐掔儫娴嬭瘯
```

`pyproject.toml` 灏?`hooks/` 鍔犲叆 `pythonpath`锛屼娇 hook 娴嬭瘯涓殑 `from metrics import ...` 鏃犻渶瀹夎浠讳綍鍖呭嵆鍙В鏋愩€傚叧浜庣紪鍐欐柊娴嬭瘯锛岃鍙傞槄 [娴嬭瘯](testing.md)銆?
---

## docs/

涓庝唬鐮佸叡瀛樹簬浠撳簱鐨勪汉绫诲彲璇绘枃妗ｃ€?
| 璺緞 | 鍐呭 |
|------|-----------------|
| `docs/hooks.md` | 姣忎釜 hook 鐨勭簿纭弬鑰冿紙閲嶅啓鍚庣増鏈級 |
| `docs/versioning.md` | 鐗堟湰鏂规涓庡崌绾ц涓?|
| `docs/wiki/` | 闈㈠悜鐢ㄦ埛鍜岃础鐚€呯殑 Wiki |
| `docs/contributing/` | 鍏变韩寮曠敤 schema銆佸彂鐗堟竻鍗?|
| `docs/update/` | `next.md`锛堝緟鍙戝竷鍙樻洿锛夊強褰掓。鐨?`vX.Y.Z.md` 鏂囦欢 |
| `docs/reference/` | API 鍜岄厤缃弬鑰冨瓨鏍?|

---

## shell/

璐＄尞鑰呬粠缁堢杩愯鐨勪袱涓搷浣滅殑钖勫寘瑁呰剼鏈細

- `publish.sh` / `publish.ps1` 鈥?濮旀墭璋冪敤 `python tools/publish.py`
- `report.sh` / `report.bat` 鈥?杩愯 `python -m hooks.metrics.reporter`锛屼粠 JSONL metrics 鏂囦欢鐢熸垚 HTML 鎶ュ憡

---

## migrations/

`tools/migrate.py` 鍦ㄤ换浣曢潪 MAJOR 鍗囩骇鏃惰繍琛岀殑杩佺Щ鑴氭湰銆傝剼鏈洿鎺ユ斁鍦?`migrations/` 涓嬶紝鎸?UTC 鏃堕棿鎴冲懡鍚嶏紙`<YYYYMMDDhhmmss>_<slug>.py`锛夛紝鎸夋椂闂村簭鎵ц銆傛瘡涓洰鏍囬」鐩湪 `.godotmaker/applied_migrations.json` 閲岀嫭绔嬭拷韪凡搴旂敤鐨?ID锛涙暣濂楁満鍒朵笌浜у搧 MAJOR.MINOR.PATCH 瀹屽叏瑙ｈ€︺€侻AJOR 鍗囩骇瀹屽叏璺宠繃杩佺Щ銆佹敼鐢?`--force` 骞插噣閲嶈锛岄噸瑁呭悗 `baseline_applied()` 浼氭妸鎵€鏈夊綋鍓嶈縼绉婚噸鏂版爣璁颁负宸插簲鐢ㄣ€傚畬鏁村崌绾ф祦绋嬭 [鍙戠増娴佺▼](release-process.md)銆?
