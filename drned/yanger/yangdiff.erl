%%%----------------------------------------------------------------%%%
%%% @doc Yanger diff                                               %%%
%%% Gives diff of two modules                                      %%%
%%%----------------------------------------------------------------%%%

-module(yangdiff).
-behaviour(yanger_plugin).

-export([init/1]).

-export([stmt2line/1]).

-include_lib("yanger/include/yang.hrl").

init(Ctx0) ->
    Ctx1 = yanger_plugin:register_error_codes(Ctx0,
                                             [
                                              {invalidargs,
                                               'error',
                                               "Need two modules to compare"},
                                              {not_found,
                                               'error',
                                               "Given module file not found"},
                                              {samerevision,
                                               'error',
                                               "Given modules have same revision, please use --diff-left to specify 'left' file(s) to diff"}
                                             ]),
    Ctx2 = yanger_plugin:register_output_format(
             Ctx1, 'diff', _AllowErrors = false, fun emit/3),
    Ctx3 = yanger_plugin:register_option_specs(Ctx2, option_specs()),
    _Ctx4 = add_hooks(Ctx3).

add_hooks(Ctx0) ->
    _Ctx1 = yanger_plugin:register_hook(Ctx0, #hooks.post_mk_sn,
                                        fun(Ctx, Node, Mode, UsesPos, Ancestors) ->
                                                SkipChoice = proplists:get_value(diff_skip_choice, Ctx#yctx.options),
                                                if (UsesPos == undefined)
                                                   andalso (Mode == 'grouping')
                                                   andalso (Node#sn.kind /= 'case') ->
                                                        PMap0 = yang:map_insert('rel_grp_path', rel_grp_path([A || A <- Ancestors, A#sn.kind /= 'case'], [], SkipChoice), Node#sn.pmap),
                                                        PMap1 = yang:map_insert('grp_module', Node#sn.module, PMap0),
                                                        UpdNode = Node#sn{pmap=PMap1};
                                                   true -> UpdNode = Node
                                                end,
                                                { Ctx, UpdNode }
                                        end).



rel_grp_path([], RelPath, _SkipChoice) ->
    RelPath;
rel_grp_path([Parent|GrandParents], RelPath, SkipChoice) ->
    if Parent#sn.kind == 'choice' ->
            case SkipChoice of
                true ->
                    rel_grp_path(GrandParents, RelPath, SkipChoice);
                false ->
                    %% must inject placeholder for case, since Ancestors will only contain explicit case-nodes
                    rel_grp_path(GrandParents, [#sn{name='<case>', kind='case'}|[Parent|RelPath]], SkipChoice)
            end;
       true -> rel_grp_path(GrandParents, [Parent|RelPath], SkipChoice)
    end.

option_specs() ->
    [{"Diff output specific options:",
      [
       %% --diff-json
       {diff_json, undefined, "diff-json", {boolean, false},
        "Output diff in json intermediate format"},
       %% --diff-incompatible
       {diff_incompatible, undefined, "diff-incompatible", {boolean, false},
        "Show backwards-incompatible changes"},
       %% --diff-new
       {diff_new, undefined, "diff-new", {boolean, false},
        "No left-module, the right module is a new module, force to show everything as new"},
       %% --diff-left
       {diff_left, undefined, "diff-left", string,
        "Use this option to give <left-file(s)> when generating diff between two files with same revision, or when generating diff of several modules (i.e. for several modules, repeat --diff-left=<left-file-N>)"},
       %% --diff-left-path
       {diff_left_path, undefined, "diff-left-path", string,
        "Use this option to give <path> (like -p) of YANG modules for left module(s) if needs to be different from right (e.g. changed imports)"},
       %% --diff-keep-ns
       {diff_keep_ns, undefined, "diff-keep-ns", {boolean, false},
        "Keep namespaces in paths"},
       %% --diff-skip-choice
       {diff_skip_choice, undefined, "diff-skip-choice", {boolean, false},
        "Skips choice/case nodes in diff"},
       %% --diff-include
       {diff_include, undefined, "diff-include", string,
        "Include only given path(s) in diff"},
       %% --diff-exclude
       {diff_exclude, undefined, "diff-exclude", string,
        "Exclude given path(s) from diff"},
       %% --diff-include-parents
       {diff_include_parents, undefined, "diff-include-parents", {boolean, false},
        "When dumping diff to json, include all parents of every node in diff"},
       %% --diff-line-numbers
       {inc_linenums, undefined, "diff-line-numbers", {boolean, false},
        "Include line-number for each node."},
       %% --diff-main-module
       {main_module, undefined, "diff-main-module", string,
        "If only interested in diff in one of given modules (e.g. if several modules are just augmenting the main-module)."}
      ]
     }].

-spec emit(#yctx{}, [#module{}], io:device()) -> [].
emit(RightCtx, Mods, Fd) ->
    LeftFiles = proplists:get_all_values(diff_left, RightCtx#yctx.options),
    LeftPath = proplists:get_value(diff_left_path, RightCtx#yctx.options),
    DiffNewMod = proplists:get_value(diff_new, RightCtx#yctx.options),

    case Mods of
        [ModRight|[ModLeft|[]]] when LeftFiles == [] ->
            if (ModLeft#module.modulename == ModRight#module.modulename)
               andalso (ModLeft#module.modulerevision == ModRight#module.modulerevision) ->
                    [#yerror{level='error', pos={"<input>", 0}, code=samerevision, args=[]}];
               true ->
                    emit_diff(RightCtx, Fd, [ModLeft], [ModRight]),
                    []
            end;
        ModsRight when LeftFiles /= [] ->
            PMapExt =
                lists:foldl(fun(ExtMod, PMap) ->
                                    yang:map_insert(ExtMod#module.modulename, ExtMod#module.groupings, PMap)
                            end, RightCtx#yctx.pmap, ModsRight),
            RightCtx1 = RightCtx#yctx{ pmap = PMapExt },
            case load_yang_modules(LeftFiles, LeftPath, RightCtx1) of
                not_found -> [#yerror{level='error', pos={"<input>", 0}, code=not_found, args=[]}];
                nothing -> [#yerror{level='error', pos={"<input>", 0}, code=invalidargs, args=[]}];
                { LeftCtx, ModsLeft1 } ->
                    %% !!! ModsLeft1 = [ Mod || {_ModRev, Mod } <- yang:map_to_list(LeftCtx#yctx.modrevs) ],
                    RightCtx2 = RightCtx1#yctx{ pmap = yang:map_insert('left_ctx', LeftCtx, RightCtx1#yctx.pmap) },
                    emit_diff(RightCtx2, Fd, ModsLeft1, ModsRight),
                    []
            end;
        [ModRight] when LeftFiles == [] andalso DiffNewMod ->
            EmptyMod = #module{ name=ModRight#module.name, children = [], modulerevision = 'undefined', namespace = ModRight#module.namespace },
            emit_diff(RightCtx, Fd, [EmptyMod], [ModRight]),
            [];
        _  -> [#yerror{level='error', pos={"<input>", 0}, code=invalidargs, args=[]}]
    end.

load_yang_modules(Files, Path, RightCtx) ->
    Ctx0 = yanger:create_ctx([]),
    Opts0 = lists:filter(fun({Name, _Val}) -> Name /= 'format' end, RightCtx#yctx.options),
    Opts1 =
        case Path of
            undefined ->
                Opts0;
            _ ->
                [{ 'path', Path }|lists:filter(fun({Name, _Val}) ->
                                                       Name /= 'path'
                                               end, Opts0)]
        end,
    { Ctx1, _Opts } = yanger:convert_options(Ctx0, Opts1),
    Ctx2 = add_hooks(Ctx1),
    { _Ctx3, _Modules } =
        lists:foldl(fun(F, { AccCtx0, AccModules }) ->
                            case yang:add_file(AccCtx0, F) of
                                {true, AccCtx1, Module} ->
                                    AccCtx2 = AccCtx1#yctx{ pmap = yang:map_insert(Module#module.modulename, Module#module.groupings, AccCtx1#yctx.pmap) },
                                    { AccCtx2, [Module|AccModules] };
                                {false, _, _} ->
                                    io:format("Error parsing file ~s~n", [F]),
                                    throw(lists:flatten(io_lib:format("Error loading modules... (~s)", [F])))
                            end
                    end, { Ctx2, [] }, Files).

-record(diff_state,
        {
         skip_choice,
         include_paths,
         exclude_paths
        }).

emit_diff(Ctx, Fd, ModsLeft, ModsRight) ->
    EmitJson = proplists:get_value(diff_json, Ctx#yctx.options),

    IncludePaths = get_paths_from_option(Ctx, diff_include),
    ExcludePaths = get_paths_from_option(Ctx, diff_exclude),
    SkipChoice = proplists:get_value(diff_skip_choice, Ctx#yctx.options),

    State = #diff_state{
               skip_choice    = SkipChoice,
               include_paths  = IncludePaths,
               exclude_paths  = ExcludePaths
              },

    ModSortFn = fun(LMod, RMod) -> LMod#module.name =< RMod#module.name end,
    SortedLeft0 = lists:sort(ModSortFn, ModsLeft),
    SortedRight0 = lists:sort(ModSortFn, ModsRight),

    {SortedLeft, SortedRight} =
        case proplists:get_value(main_module, Ctx#yctx.options) of
            undefined ->
                {SortedLeft0, SortedRight0};
            MainModule ->
                {lists:filter(fun(M) -> M#module.name == ?l2a(MainModule) end, SortedLeft0),
                 lists:filter(fun(M) -> M#module.name == ?l2a(MainModule) end, SortedRight0)}
        end,

    EmptyDiff = { _New = [], _Rem = [], _Chg = [], _Incompats = maps:new() },
    Diff = lists:foldl(fun({ ModLeft, ModRight }, AccDiff) ->
                               diff_traverse_children({[],[]}, AccDiff,
                                                      filter_include_exclude(flatten_choices(ModLeft#module.children, State), State),
                                                      filter_include_exclude(flatten_choices(ModRight#module.children, State), State),
                                                      State)
                       end, EmptyDiff, lists:zip(SortedLeft, SortedRight)),
    case EmitJson of
        true ->
            emit_json_diff(Fd, SortedLeft, SortedRight, Diff, Ctx);
        false  ->
            emit_short_diff(Fd, SortedLeft, SortedRight, Diff, Ctx)
    end.

get_paths_from_option(Ctx, OptionName) ->
    [[?l2a(Step) || Step <- string:tokens(Path,"/")] ||
        Path <- proplists:get_all_values(OptionName, Ctx#yctx.options)].

emit_short_diff(Fd, _ModsLeft, _ModsRight, Diff, Ctx) ->
    ShowIncompats = proplists:get_value(diff_incompatible, Ctx#yctx.options),

    { NewNodes, RemNodes, ChgNodes, Incompats } = Diff,
    { _LChgNodes, RChgNodes } = lists:unzip(ChgNodes),
    io:format(Fd, "~n", []),
    case ShowIncompats of
        true ->
            IncompatsByType0 = lists:foldl(fun({ _, {P,IList}}, ByTypeMap) ->
                                                   case IList of
                                                       [{ T, _ }] ->
                                                           PathsOfType = maps:get(T, ByTypeMap, []),
                                                           maps:put(T, [P|PathsOfType], ByTypeMap);
                                                       _ ->
                                                           { MultiT, _ } = lists:unzip(IList),
                                                           PathsOfType = maps:get(MultiT,
                                                                                  ByTypeMap, []),
                                                           maps:put(MultiT,
                                                                    [P|PathsOfType], ByTypeMap)
                                                   end
                                           end, maps:new(), maps:to_list(Incompats)),
            lists:foreach(fun({T, PathsOfType}) ->
                                  emit_path_list(Fd,
                                                 bold_str(io_lib:format("Incompatible ~p", [T])),
                                                 PathsOfType, Ctx)
                          end, maps:to_list(IncompatsByType0));
        false ->
            DataNodesFn = fun(Nodes) ->
                                  lists:filter(fun([Node|_]) ->
                                                       (not lists:member(Node#sn.kind, ['choice', 'case', 'container']))
                                                           orelse (Node#sn.kind == 'container'
                                                                   andalso (yang:search_one_substmt('presence', Node#sn.stmt) /= false)) end, Nodes)
                          end,
            LeftCtx = case yang:map_lookup('left_ctx', Ctx#yctx.pmap) of
                          none -> Ctx;
                          { value, LCtx } -> LCtx
                      end,
            emit_path_list(Fd, bold_str("New nodes"), DataNodesFn(NewNodes), Ctx),
            emit_path_list(Fd, bold_str("Removed nodes"), DataNodesFn(RemNodes), LeftCtx),
            emit_path_list(Fd, bold_str("Changed nodes"), DataNodesFn(RChgNodes), Ctx)
    end.

bold_str(Str) ->
    io_lib:format("\x1b[1m~s\x1b[0m", [Str]).

emit_path_list(Fd, Title, PathList, Ctx) ->
    KeepNS = proplists:get_value(diff_keep_ns, Ctx#yctx.options),

    { PathListNoGroupings, CollapseMap } = collapse_groupings(PathList, Ctx),
    case (length(PathListNoGroupings) > 0) orelse (maps:size(CollapseMap) > 0) of
        true ->
            io:format(Fd, "~s~n  ~s~n", [Title, string:join(lists:sort([path_to_string(Path, KeepNS) || Path <- PathListNoGroupings]), "\n  ")]),
            lists:foreach(fun({ GrpKey, RelPathMap}) ->
                                  { GrpName, GrpModRef, Line } = GrpKey,
                                  { GrpMod, _ } = GrpModRef,
                                  RelPathMapList = maps:to_list(RelPathMap),
                                  UsedAtRelPathMap =
                                      lists:foldl(fun({ RelPath, UsedAtList }, UARPMap) ->
                                                          UsedAtPaths = lists:sort([path_to_string(lists:reverse(UsedAt), KeepNS) ++ "/..."
                                                                                    %% ++ io_lib:format(" (line: ~p)", [stmt2line((lists:last(UsedAt))#sn.stmt)])
                                                                                    || UsedAt <- UsedAtList]),
                                                          RelPathList = maps:get(UsedAtPaths, UARPMap, []),
                                                          maps:put(UsedAtPaths, [RelPath|RelPathList], UARPMap)
                                                  end, maps:new(), RelPathMapList),
                                  ModGrpName =
                                      case GrpMod /= (lists:nth(1, lists:nth(1, PathList)))#sn.module#module.name of
                                          true -> io_lib:format("~s:~s", [GrpMod, GrpName]);
                                          false -> GrpName
                                      end,
                                  lists:foreach(fun({ UsedAtPaths, RelPaths }) ->
                                                        io:format(Fd, "~n  ~s in grouping ~s@~p", [Title, ModGrpName, Line]),
                                                        io:format(Fd, "~n  ~s~n    ~s~n",
                                                                  [string:join(UsedAtPaths, "\n  "),
                                                                   string:join(lists:sort(RelPaths), "\n    ")])
                                                end, maps:to_list(UsedAtRelPathMap))

                          end,
                          lists:sort(fun({{LGrp, _, _ }, _}, {{RGrp, _, _}, _}) -> LGrp =< RGrp end, maps:to_list(CollapseMap)));
        false ->
            io:format(Fd, "~s none~n", [Title])
    end,
    io:format(Fd, "~n", []).

stmt2line(Stmt) ->
    { _, _, Pos, _ } = Stmt,
    _Line = element(2, Pos).

collapse_groupings(PathList0, Ctx) ->
    CollapseFn =
        fun([Node|ParentPath], { NewPathList, CollapseMap }) ->
                case in_uses(Node, lists:reverse(ParentPath), Ctx) of
                    false -> { [[Node|ParentPath]|NewPathList], CollapseMap };
                    { _, undefined } ->
                        { [[Node|ParentPath]|NewPathList], CollapseMap };
                    { UsedInPath, Grouping } ->
                        GrpKey = { Grouping#grouping.name, Grouping#grouping.moduleref, stmt2line(Grouping#grouping.stmt) },
                        RelPathMap0 = maps:get(GrpKey, CollapseMap, maps:new()),
                        RelPath = rel_path_to_string([Node|lists:sublist(ParentPath, length(ParentPath) - length(UsedInPath))]),
                        UseAtList = maps:get(RelPath, RelPathMap0, []),
                        RelPathMap1 = maps:put(RelPath, [UsedInPath|UseAtList], RelPathMap0),
                        NewCollapseMap = maps:put(GrpKey, RelPathMap1, CollapseMap),
                        { NewPathList, NewCollapseMap }
                end
        end,
    { _PathList1, _CollapseMap0 } = lists:foldl(CollapseFn, { [], maps:new() }, PathList0).

emit_json_diff(Fd, ModsLeft, ModsRight, Diff, Ctx) ->
    KeepNS = proplists:get_value(diff_keep_ns, Ctx#yctx.options),

    { NewNodes, RemNodes, ChgNodes, Incompats } = Diff,
    { LChgNodes, RChgNodes } = lists:unzip(ChgNodes),

    PFn = fun(NPList) -> [path_to_string(NodeP, KeepNS) || NodeP <- NPList] end,
    QFn = fun(SPList) -> [io_lib:format("\"~s\"", [StrP]) || StrP <- SPList] end,

    NewPaths = PFn(NewNodes),
    RemPaths = PFn(RemNodes),
    ChgPaths = PFn(LChgNodes),
    NewPathsQ = QFn(NewPaths),
    RemPathsQ = QFn(RemPaths),
    ChgPathsQ = QFn(ChgPaths),

    io:format(Fd, "{~n", []),
    io:format(Fd, "  \"left_rev\": [ ~s ],~n", [string:join([io_lib:format("\"~s\"", [Mod#module.modulerevision]) || Mod <- ModsLeft], ", ")]),
    io:format(Fd, "  \"right_rev\": [ ~s ],~n", [string:join([io_lib:format("\"~s\"", [Mod#module.modulerevision]) || Mod <- ModsRight], ", ")]),
    io:format(Fd, "  \"left_ns\": [ ~s ],~n", [string:join([io_lib:format("\"~s\"", [Mod#module.namespace]) || Mod <- ModsLeft], ", ")]),
    io:format(Fd, "  \"right_ns\": [ ~s ],~n", [string:join([io_lib:format("\"~s\"", [Mod#module.namespace]) || Mod <- ModsRight], ", ")]),
    io:format(Fd, "  \"new_nodes\": [~n    ~s~n  ],~n", [string:join(NewPathsQ, ",\n    ")]),
    io:format(Fd, "  \"rem_nodes\": [~n    ~s~n  ],~n", [string:join(RemPathsQ, ",\n    ")]),
    io:format(Fd, "  \"diff_nodes\": [~n    ~s~n  ],~n", [string:join(ChgPathsQ, ",\n    ")]),
    io:format(Fd, "  \"incompat_nodes\": {~n    ~s~n  },~n", [string:join([io_lib:format("\"~s\": [ ~s ]",
                                                                                         [path_to_string(P, KeepNS),
                                                                                          string:join([io_lib:format("\"~s\"", [Type]) ||
                                                                                                          Type <- begin { TList, _ } = lists:unzip(IList),
                                                                                                                        TList
                                                                                                                  end], ",")])
                                                                           || { _, {P,IList}} <- maps:to_list(Incompats)],  ",\n    ")]),

    { NewNodeInfo, OldNodeInfo } =
        case proplists:get_value(diff_include_parents, Ctx#yctx.options) of
            true ->
                NewPathsSet = sets:from_list(NewPaths ++ ChgPaths),
                OldPathsSet = sets:from_list(RemPaths ++ ChgPaths),
                AllNewNodes = NewNodes ++ RChgNodes,
                AllOldNodes = RemNodes ++ LChgNodes,
                { _, NewAddedParents } =
                    lists:foldl(fun(NPath, {AddedSet0, AddedParents0}) ->
                                        add_parents(NPath, AddedSet0, AddedParents0, KeepNS)
                                end, { NewPathsSet, [] }, AllNewNodes),
                { _, OldAddedParents } =
                    lists:foldl(fun(NPath, {AddedSet0, AddedParents0}) ->
                                        add_parents(NPath, AddedSet0, AddedParents0, KeepNS)
                                end, { OldPathsSet, [] }, AllOldNodes),
                { AllNewNodes ++ NewAddedParents,
                  AllOldNodes ++ OldAddedParents };
            false ->
                AddListsFn =
                    fun([Path|RevParentPath], { AddedPathsSet, AddedParents }) ->
                            PPathStr = path_to_string(RevParentPath, KeepNS),
                            case not sets:is_element(PPathStr, AddedPathsSet)
                                andalso (RevParentPath /= []) of
                                true ->
                                    [Parent|_] = RevParentPath,
                                    case Parent#sn.keys /= 'undefined'
                                        andalso lists:member(Path#sn.name, Parent#sn.keys) of
                                        true ->
                                            { sets:add_element(PPathStr, AddedPathsSet),
                                              [RevParentPath|AddedParents] };
                                        false ->
                                            { AddedPathsSet, AddedParents }
                                    end;
                                false ->
                                    { AddedPathsSet, AddedParents }
                            end
                    end,
                %% Also add list node if key node(s) changed
                ChgPathsSet = sets:from_list(ChgPaths),
                { _, RChgLists } = lists:foldl(AddListsFn, { ChgPathsSet, [] }, RChgNodes),
                { _, LChgLists } = lists:foldl(AddListsFn, { ChgPathsSet, [] }, LChgNodes),
                { NewNodes ++ RChgNodes ++ RChgLists,
                  RemNodes ++ LChgNodes ++ LChgLists }
        end,

    EmitFn = fun(Path, JsonList) ->
                     [Node|RevParentPath] = Path,
                     Json = emit_node_json_diff(Node, RevParentPath, Ctx),
                     [Json|JsonList]
             end,
    io:format(Fd, "  \"new_node_info\": {~n~s~n  },~n",
              [string:join(lists:foldl(EmitFn, [], NewNodeInfo), ",\n")]),
    io:format(Fd, "  \"old_node_info\": {~n~s~n  }~n",
              [string:join(lists:foldl(EmitFn, [], OldNodeInfo), ",\n")]),
    io:format(Fd, "}~n", []).

add_parents([], AddedSet, AddedParents, _KeepNS) ->
    { AddedSet, AddedParents };
add_parents([Node|RevParents], AddedSet0, AddedParents0, KeepNS) ->
    { AddedSet1, AddedParents1 } = add_parents_impl([Node|RevParents], AddedSet0, AddedParents0, KeepNS),
    add_parents(RevParents, AddedSet1, AddedParents1, KeepNS).

add_parents_impl(Path, AddedSet, AddedParents, KeepNS) ->
    SP = path_to_string(Path, KeepNS),
    case not sets:is_element(SP, AddedSet) of
        true ->
            { sets:add_element(SP, AddedSet),
              [Path|AddedParents] };
        false ->
            { AddedSet, AddedParents }
    end.

emit_node_json_diff(Node, ParentPath, Ctx) ->
    KeepNS = proplists:get_value(diff_keep_ns, Ctx#yctx.options),
    Path = [Node|ParentPath],
    PathStr = path_to_string(Path, KeepNS),
    UsesInfo =  emit_uses_info(Node, lists:reverse(ParentPath), Ctx),
    { NodeJson, _NewTypeDefs, _Children } =
        jsondump:emit_sn_json(Node, PathStr, maps:new(), UsesInfo,
                              fun({Kw, _, _, _}) ->
                                      not lists:member(Kw, [leaf, 'leaf-list', container, list, key, choice, 'case'])
                              end, Ctx#yctx.options),
    NodeJson.

emit_uses_info(Node, ParentPath, Ctx) ->
    KeepNS = proplists:get_value(diff_keep_ns, Ctx#yctx.options),
    case in_uses(Node, ParentPath, Ctx) of
        false -> "";
        { UsedInPath, Grouping } when is_record(Grouping, grouping) ->
            { _, _, Pos, _ } = Grouping#grouping.stmt,
            Line = element(2, Pos),
            io_lib:format("      \"in_uses\": \"~s:~s@~p\",~n", [path_to_string(lists:reverse(UsedInPath), KeepNS), Grouping#grouping.name, Line]);
        { _UsedInPath, _ } ->
            %% Refined nodes can't be found in grouping when we can't find uses stmt (e.g. a refined uses inside a case when 'SkipChoices')
            %% io:format("POSSIBLE refine: ~s in ~s~n", [Node#sn.name, path_to_string(lists:reverse(UsedInPath), false)]),
            ""
    end.

in_uses(Node, ParentPath, Ctx) ->
    SkipChoice = proplists:get_value(diff_skip_choice, Ctx#yctx.options),
    case yang:map_lookup('rel_grp_path', Node#sn.pmap) of
        none -> false;
        { value, RelGrpPath } ->
            { _, DefMod } = yang:map_lookup('grp_module', Node#sn.pmap),
            UsedInPath = lists:sublist(ParentPath, length(ParentPath)-length(RelGrpPath)),
            case UsedInPath /= [] of
                true ->
                    LookFor = case length(RelGrpPath) > 0 of
                                  true -> lists:nth(length(UsedInPath)+1, ParentPath);
                                  false -> Node
                              end,
                    %% io:format("LOOKFOR: (~s) ~p (~p) in ~p~n", [rel_path_to_string(RelGrpPath), LookFor#sn.name, Node#sn.name, (lists:last(UsedInPath))#sn.name]),
                    Grouping =
                        case find_grouping(LookFor, lists:last(UsedInPath), SkipChoice) of
                            undefined ->
                                %% When a uses is augmented into a node from
                                %% another uses there is no uses stmt in the node
                                %% itself
                                case find_grouping_all(LookFor, (lists:last(UsedInPath))#sn.groupings, SkipChoice) of
                                    undefined ->
                                        %% io:format("TRY in MOD: ~s~n", [DefMod#module.modulename]),
                                        case yang:map_lookup(DefMod#module.modulename, Ctx#yctx.pmap) of
                                            { value, ExtModGrps } ->
                                                %% One more try, its from an imported grouping
                                                find_grouping_all(LookFor, ExtModGrps, SkipChoice);
                                            none ->
                                                undefined
                                        end;
                                    Grp when is_record(Grp, grouping) ->
                                        Grp
                                end;
                            Grp when is_record(Grp, grouping) -> Grp
                        end,
                    { UsedInPath, Grouping };
                false ->
                    %% The uses is on top-level of module
                    false
            end
    end.

find_grouping(Node, UsedIn, SkipChoice) ->
    UsedGrps = [Arg || { _, Arg, _, _ } <- yang:search_all_stmts('uses', UsedIn#sn.stmt)],
    case find_grouping0(Node, yang:map_iterator((UsedIn#sn.groupings)#groupings.map), UsedGrps, SkipChoice) of
        undefined ->
            case ((UsedIn#sn.groupings)#groupings.parent) of
                undefined -> undefined;
                GrpsParent -> find_grouping0(Node, yang:map_iterator(GrpsParent#groupings.map), UsedGrps, SkipChoice)
            end;
        Grp -> Grp
    end.

find_grouping_all(Node, Groupings, SkipChoice) ->
    case find_grouping_all_impl(Node, Groupings, SkipChoice) of
        undefined ->
            if is_record(Groupings#groupings.parent, grouping) ->
                    find_grouping_all(Node, Groupings#groupings.parent, SkipChoice);
               true ->
                    %% couldn't find it, probably a refine, when uses stmt not found (see above)
                    undefined
            end;
        Grouping -> Grouping
    end.

find_grouping_all_impl(Node, Groupings, SkipChoice) when is_record(Groupings, groupings) ->
    find_grouping_all_impl(Node, yang:map_to_list(Groupings#groupings.map), SkipChoice);
find_grouping_all_impl(Node, [{ _Name, Grouping }|Rest], SkipChoice) ->
    case lists:any(fun(C) -> nodes_equal(Node, C) end, flatten_choices(Grouping#grouping.children, SkipChoice)) of
        true ->
            Grouping;
        false ->
            find_grouping_all_impl(Node, Rest, SkipChoice)
    end;
find_grouping_all_impl(_Node, [], _SkipChoice) ->
    undefined;
find_grouping_all_impl(_Node, undefined, _SkipChoice) ->
    undefined.

find_grouping0(Node, Iter0, UsedGrps, SkipChoice) ->
    case yang:map_next(Iter0) of
        {_, Grp, Iter1} ->
            case lists:member(Grp#grouping.name, UsedGrps)
                andalso lists:member(Node#sn.name, [C#sn.name || C <- flatten_choices(Grp#grouping.children, SkipChoice)]) of
                true ->
                    %% io:format("FOUND: ~s ~s in ~s ~n", [Node#sn.kind, Node#sn.name, Grp#grouping.name]),
                    Grp;
                false ->
                    %% io:format("CHECK GRP, ~s NOT FOUND: ~s ~p~n", [Node#sn.name, Grp#grouping.name, UsedGrps]),
                    find_grouping0(Node, Iter1, UsedGrps, SkipChoice)
            end;
        none ->
            undefined
    end.

diff_nodes(ParentPath, Diff, Left, Right, State) ->
    IsEq = nodes_equal(Left, Right),
    { NewNodes, RemNode, ChgNodes0, Incompats0 } = Diff,
    { LParentPath, RParentPath } = ParentPath,
    Path = {[Left|LParentPath], [Right|RParentPath]},
    case IsEq of
        true ->
            Incompats1 = Incompats0,
            ChgNodes1 = ChgNodes0;
        false ->
            Incompats1 = check_incompatible_changes(RParentPath, Left, Right, Incompats0),
            ChgNodes1 = [Path|ChgNodes0]
    end,
    NewDiff = { NewNodes, RemNode, ChgNodes1, Incompats1 },
    NewState = update_include_exclude(Left, State),
    diff_traverse_children(Path, NewDiff,
                           filter_include_exclude(flatten_choices(Left#sn.children, NewState), NewState),
                           filter_include_exclude(flatten_choices(Right#sn.children, NewState), NewState),
                           NewState).

incompat_keyword_change(Left, Right) ->
    (Left#sn.kind /= Right#sn.kind)
        andalso not incompat_empty_to_presence(Left, Right).

incompat_empty_to_presence(Left, Right) ->
    (Left#sn.kind == 'leaf')
        andalso is_record((defined_type(Left#sn.type))#type.type_spec, empty_type_spec)
        andalso (Right#sn.kind == 'container')
        andalso (yang:search_one_substmt('presence', Right#sn.stmt) /= false).

incompat_int_range_narrowing(#sn{ kind = Kind, type = LType },
                             #sn{ kind = Kind, type = RType })
  when is_record(LType, type) ->
    LTypeSpec = (defined_type(LType))#type.type_spec,
    RTypeSpec = (defined_type(RType))#type.type_spec,
    case is_record(LTypeSpec, integer_type_spec)
        andalso is_record(RTypeSpec, integer_type_spec) of
        true ->
            LMin = LTypeSpec#integer_type_spec.min,
            LMax = LTypeSpec#integer_type_spec.max,
            LRange0 = LTypeSpec#integer_type_spec.range,
            RMin = RTypeSpec#integer_type_spec.min,
            RMax = RTypeSpec#integer_type_spec.max,
            RRange0 = RTypeSpec#integer_type_spec.range,
            LRange1 = case LRange0 of
                          [] ->
                              [{LMin, LMax}];
                          _ ->
                              lists:map(fun(Rng) -> if not is_tuple(Rng) -> { Rng, Rng }; true -> Rng end end, LRange0)
                      end,
            RRange1 = case RRange0 of
                          [] ->
                              [{RMin, RMax}];
                          _ ->
                              lists:map(fun(Rng) -> if not is_tuple(Rng) -> { Rng, Rng }; true -> Rng end end, RRange0)
                      end,
            not lists:all(fun ({ LSMin, LSMax }) ->
                                  lists:any(fun({ RSMin, RSMax }) ->
                                                    (LSMin >= RSMin) andalso (LSMax =< RSMax)
                                            end, RRange1)
                          end, LRange1);
        false ->
            false
    end;
incompat_int_range_narrowing(_, _) ->
    false.

incompat_enum_change(#sn{ kind = Kind, type = LType },
                     #sn{ kind = Kind, type = RType })
  when is_record(LType, type) ->
    LTypeSpec = (defined_type(LType))#type.type_spec,
    RTypeSpec = (defined_type(RType))#type.type_spec,
    case is_record(LTypeSpec, enumeration_type_spec)
        andalso is_record(RTypeSpec, enumeration_type_spec) of
        true ->
            LEnums = LTypeSpec#enumeration_type_spec.enums,
            REnums = RTypeSpec#enumeration_type_spec.enums,
            not lists:prefix(LEnums, REnums);
        false ->
            false
    end;
incompat_enum_change(_, _) ->
    false.

incompat_string_length_narrowing(#sn{ kind = Kind, type = LType },
                                 #sn{ kind = Kind, type = RType })
  when is_record(LType, type) ->
    LTypeSpec = (defined_type(LType))#type.type_spec,
    RTypeSpec = (defined_type(RType))#type.type_spec,
    case is_record(LTypeSpec, string_type_spec)
        andalso is_record(RTypeSpec, string_type_spec) of
        true ->
            LMin = LTypeSpec#string_type_spec.min,
            LMax = LTypeSpec#string_type_spec.max,
            RMin = RTypeSpec#string_type_spec.min,
            RMax = RTypeSpec#string_type_spec.max,
            (LMin < RMin) orelse (LMax > RMax);
        false ->
            false
    end;
incompat_string_length_narrowing(_, _) ->
    false.

incompat_type_narrowing(Left, Right) ->
    IsLeaf = (Left#sn.kind == Right#sn.kind)
        andalso ((Left#sn.kind == 'leaf') orelse (Left#sn.kind == 'leaf-list')),
    IsLeaf andalso (not same_type(Left, Right))
        andalso incompat_type_narrowing_impl((defined_type(Left#sn.type))#type.type_spec,
                                             (defined_type(Right#sn.type))#type.type_spec).

incompat_type_narrowing_impl(LTypeSpec, RTypeSpec) when is_tuple(LTypeSpec) andalso is_tuple(LTypeSpec) ->
    (erlang:element(1, LTypeSpec) /= erlang:element(1, RTypeSpec))
        andalso (not is_record(RTypeSpec, string_type_spec)
                 andalso not is_record(RTypeSpec, union_type_spec));
incompat_type_narrowing_impl(LTypeSpec, RTypeSpec) ->
    LTypeSpec /= RTypeSpec.

incompat_type_empty_change(Left, Right) when is_record(Left#sn.type, type)
                                             andalso is_record(Right#sn.type, type) ->
    case (defined_type(Left#sn.type))#type.type_spec of
        #empty_type_spec{} ->
            not is_record((defined_type(Right#sn.type))#type.type_spec, empty_type_spec);
        _ ->
            false
    end;
incompat_type_empty_change(_, _) ->
    false.

incompat_presence_change(#sn{ kind=Kind, stmt=LStmt },
                         #sn{ kind=Kind, stmt=RStmt }) when Kind == 'container' ->
    LPresence = get_substmt_arg('presence', LStmt),
    RPresence = get_substmt_arg('presence', RStmt),
    not ((LPresence == RPresence)
         orelse (LPresence /= false andalso RPresence /= false));
incompat_presence_change(_, _) ->
    false.

incompat_mandatory_change(Left, Right) ->
    LMand = get_substmt_arg('mandatory', Left#sn.stmt),
    RMand = get_substmt_arg('mandatory', Right#sn.stmt),
    (LMand /= RMand)
        andalso ((LMand == false) orelse (LMand /= true)).

incompat_must_added(Left, Right) ->
    LMust = get_substmt_arg('must', Left#sn.stmt),
    RMust = get_substmt_arg('must', Right#sn.stmt),
    (LMust == false) andalso (RMust /= false).

incompat_num_elements_shrunk(Left, Right) ->
    LMin = get_substmt_arg('min-elements', Left#sn.stmt, 0),
    LMax = get_substmt_arg('max-elements', Left#sn.stmt,  1 bsl 32),
    RMin = get_substmt_arg('min-elements', Right#sn.stmt, 0),
    RMax = get_substmt_arg('max-elements', Right#sn.stmt,  1 bsl 32),
    ((LMin < RMin) orelse (LMax > RMax)).

incompat_list_keys_change(Left, Right) ->
    (Left#sn.keys /= Right#sn.keys).

check_incompatible_changes(RParentPath, Left, Right, Incompats0) ->
    IncompatChecks = [
                      { fun incompat_keyword_change/2, keyword_change, struct_incompat },
                      { fun incompat_empty_to_presence/2, empty_to_presence, api_incompat },
                      { fun incompat_type_narrowing/2, type_narrowing, api_incompat },
                      { fun incompat_int_range_narrowing/2, int_range_narrowing, api_incompat },
                      { fun incompat_string_length_narrowing/2, string_length_narrowing, api_incompat },
                      { fun incompat_enum_change/2, enum_change, api_incompat },
                      { fun incompat_type_empty_change/2, type_empty_change, struct_incompat },
                      { fun incompat_presence_change/2, presence_change, api_incompat },
                      { fun incompat_mandatory_change/2, mandatory_change, api_incompat },
                      { fun incompat_must_added/2, must_added, api_incompat },
                      { fun incompat_num_elements_shrunk/2, num_elements_shrunk, api_incompat },
                      { fun incompat_list_keys_change/2, list_keys_change, struct_incompat }
                     ],
    case lists:foldl(fun({ IncompatFn, IncompatName, IncompatType }, IncompatAcc) ->
                             %%  {_, Name} = lists:keyfind('name', 1, erlang:fun_info(IncompatFn)),
                             case IncompatFn(Left, Right) of
                                 true ->
                                     IncompatDesc = { IncompatName, IncompatType },
                                     [IncompatDesc|IncompatAcc];
                                 false ->
                                     IncompatAcc
                             end
                     end, [], IncompatChecks) of
        [] ->
            Incompats0;
        IncompatDescs ->
            Path = [Right|RParentPath],
            maps:put(path_to_string(Path, false), { Path, IncompatDescs }, Incompats0)
    end.

nodes_equal(Left, Right) ->
    (Left#sn.name == Right#sn.name)
        andalso (Left#sn.kind == Right#sn.kind)
        andalso (Left#sn.keys == Right#sn.keys)
        andalso same_default(Left, Right)
        andalso same_type(Left, Right)
        andalso same_stmts(Left#sn.stmt, Right#sn.stmt).

same_default(#sn{ default = Def }, #sn{ default = Def }) ->
    true;
same_default(#sn{ default = { LStmt, _ }}, #sn{ default = { RStmt, _ }}) ->
    same_stmts(LStmt, RStmt);
same_default(#sn{ default = LDefs }, #sn{ default = RDefs }) when is_list(LDefs) andalso is_list(RDefs) ->
    lists:all(fun({LDef, RDef}) -> same_default(LDef, RDef) end, lists:zip(LDefs, RDefs));
same_default(_LDef, _RDef) ->
    false.

same_type(Left, Right) when is_record(Left#sn.type, type) andalso is_record(Right#sn.type, type) ->
    same_type_spec(defined_type(Left#sn.type), defined_type(Right#sn.type));
same_type(Left, Right) ->
    (Left#sn.type == Right#sn.type).

defined_type(Type) when is_record(Type#type.base, typedef) ->
    defined_type((Type#type.base)#typedef.type);
defined_type(Type) ->
    Type.

same_stmts({KW, Arg, _, LSubs}, {KW, Arg, _, RSubs}) ->
    LSubs0 = lists:filter(fun({Kw, _, _, _}) -> jsondump:is_substmt(Kw) end, LSubs),
    RSubs0 = lists:filter(fun({Kw, _, _, _}) -> jsondump:is_substmt(Kw) end, RSubs),
    SortSubsFn = fun({LKw, LArg, _, _}, {RKw, RArg, _, _}) ->
                         case LKw /= RKw of
                             true ->
                                 (LKw =< RKw);
                             false  ->
                                 (LArg =< RArg)
                         end
                 end,
    LSubs1 = lists:sort(SortSubsFn, LSubs0),
    RSubs1 = lists:sort(SortSubsFn, RSubs0),
    length(LSubs0) == length(RSubs0) andalso
        lists:all(fun({LStmt, RStmt}) -> same_stmts(LStmt, RStmt) end, lists:zip(LSubs1, RSubs1));
same_stmts(_L, _R) ->
    %% io:format("STMTS NOT EQUAL~n  ~p~n!=!=!=!=!=!=~n~p~n==========", [L, R]),
    false.

same_type_spec(LeftType, RightType) ->
    same_type_spec_impl(LeftType#type.type_spec, RightType#type.type_spec).

same_type_spec_impl(TypeSpec, TypeSpec) ->
    %% boolean + empty (no stmt() in rec.)
    true;
same_type_spec_impl(#integer_type_spec{min = Min, max = Max, range = Range},
                    #integer_type_spec{min = Min, max = Max, range = Range}) ->
    true;
same_type_spec_impl(#string_type_spec{min = Min, max = Max, length = Len, patterns = LPatterns},
                    #string_type_spec{min = Min, max = Max, length = Len, patterns = RPatterns}) ->
    length(LPatterns) == length(RPatterns) andalso
        lists:all(fun({{_, LReg, LInv}, {_, RReg, RInv}}) ->
                          (LReg == RReg) andalso (LInv == RInv) end, lists:zip(LPatterns, RPatterns));
same_type_spec_impl(#binary_type_spec{min = Min, max = Max, length = Len},
                    #binary_type_spec{min = Min, max = Max, length = Len}) ->
    true;
same_type_spec_impl(#decimal64_type_spec{fraction_digits = FD, min = Min, max = Max, range = Range},
                    #decimal64_type_spec{fraction_digits = FD, min = Min, max = Max, range = Range}) ->
    true;
same_type_spec_impl(#enumeration_type_spec{enums = Enums},
                    #enumeration_type_spec{enums = Enums}) ->
    true;
same_type_spec_impl(#bits_type_spec{bits = Bits},
                    #bits_type_spec{bits = Bits}) ->
    true;
same_type_spec_impl(#leafref_type_spec{path = Path, require_instance = ReqInst},
                    #leafref_type_spec{path = Path, require_instance = ReqInst}) ->
    true;
same_type_spec_impl(#union_type_spec{types = LTypes},
                    #union_type_spec{types = RTypes}) ->
    length(LTypes) == length(RTypes) andalso
        lists:all(fun({ LTS, RTS }) ->
                          same_type_spec(defined_type(LTS), defined_type(RTS)) end, lists:zip(LTypes, RTypes));
same_type_spec_impl(_LTypeSpec, _RTypeSpec) ->
    false.

get_substmt_arg(Kwd, Stmt) ->
    get_substmt_arg(Kwd, Stmt, false).

get_substmt_arg(Kwd, Stmt, Default) ->
    case yang:search_one_substmt(Kwd, Stmt) of
        { _, Arg, _, _ } ->
            Arg;
        _ ->
            Default
    end.

diff_traverse_children(ParentPath, Diff, LeftChildren, RightChildren, State) ->
    { NewNodes0, RemNodes0, ChgNodes, Incompats } = Diff,
    LeftNames = sets:from_list([C#sn.name || C <- LeftChildren]),
    RightNames = sets:from_list([C#sn.name || C <- RightChildren]),
    ComC = sets:intersection(LeftNames, RightNames),
    NewC = sets:subtract(RightNames, LeftNames),
    RemC = sets:subtract(LeftNames, RightNames),
    { LParentPath, RParentPath } = ParentPath,
    NewNodes1 = add_trees(RParentPath,
                          NewNodes0,
                          [CNode || CNode <-
                                        lists:filter(fun(CNode) -> sets:is_element(CNode#sn.name, NewC) end,
                                                     RightChildren)], State),
    RemNodes1 = add_trees(LParentPath,
                          RemNodes0,
                          [CNode || CNode <-
                                        lists:filter(fun(CNode) -> sets:is_element(CNode#sn.name, RemC) end,
                                                     LeftChildren)], State),
    NewDiff = { NewNodes1, RemNodes1, ChgNodes, Incompats },
    ComLeftChildren = lists:filter(fun(CNode) -> sets:is_element(CNode#sn.name, ComC) end,
                                   LeftChildren),
    ComRightChildren = order_nodes(ComLeftChildren, RightChildren),
    diff_compare_common(ParentPath, NewDiff, ComLeftChildren, ComRightChildren, State).

update_include_exclude(Node, State) ->
    IncludePaths0 = State#diff_state.include_paths,
    ExcludePaths0 = State#diff_state.exclude_paths,
    IncludePaths1 = lists:map(fun([_|Rest]) -> Rest end,
                              lists:filter(fun([Next|Rest]) ->
                                                   (Next == Node#sn.name) andalso (length(Rest) > 0) end, IncludePaths0)),
    ExcludePaths1 = lists:map(fun([_|Rest]) -> Rest end,
                              lists:filter(fun([Next|Rest]) ->
                                                   (Next == Node#sn.name) andalso (length(Rest) > 0) end, ExcludePaths0)),
    State#diff_state{ include_paths=IncludePaths1, exclude_paths=ExcludePaths1 }.

filter_include_exclude(Children0, State) ->
    IncludePaths = State#diff_state.include_paths,
    ExcludePaths = State#diff_state.exclude_paths,
    Children1 =
        if IncludePaths /= [] ->
                lists:filter(fun(C) ->
                                     lists:any(fun(Path) -> [Next|_] = Path, Next == C#sn.name end, IncludePaths)
                             end, Children0);
           true -> Children0
        end,
    _Children2 =
        if ExcludePaths /= [] ->
                lists:filter(fun(C) ->
                                     not lists:any(fun(Path) -> case Path of [Name] -> Name == C#sn.name; _ -> false end end, ExcludePaths)
                             end, Children1);
           true -> Children1
        end.

flatten_choices(Children, State) when is_record(State, diff_state) ->
    flatten_choices(Children, State#diff_state.skip_choice);
flatten_choices(Children, SkipChoice) when is_boolean(SkipChoice) ->
    case SkipChoice of
        true -> flatten_choices_impl(Children, [], SkipChoice);
        false -> Children
    end.

flatten_choices_impl([], Flattened, _SkipChoice) ->
    Flattened;
flatten_choices_impl([C|Rest], Flattened, SkipChoice) ->
    if (C#sn.kind == 'case') orelse (C#sn.kind == 'choice') ->
            Flattened1 = flatten_choices(C#sn.children, SkipChoice) ++ Flattened,
            flatten_choices_impl(Rest, Flattened1, SkipChoice);
       true ->
            flatten_choices_impl(Rest, [C|Flattened], SkipChoice)
    end.

add_trees(_, NodeList, [], _) ->
    NodeList;
add_trees(ParentPath, NodeList, [Node|Rest], State) ->
    NodeList1 = [[Node|ParentPath]|NodeList],
    NodeList2 = add_trees(ParentPath, NodeList1, Rest, State),
    NewState = update_include_exclude(Node, State),
    add_trees([Node|ParentPath], NodeList2, filter_include_exclude(flatten_choices(Node#sn.children, NewState), NewState), NewState).

diff_compare_common(_, Diff, [], [], _) ->
    Diff;
diff_compare_common(ParentPath, Diff, [Left|LeftRest], [Right|RightRest], State) ->
    NewDiff = diff_nodes(ParentPath, Diff, Left, Right, State),
    diff_compare_common(ParentPath, NewDiff, LeftRest, RightRest, State).

order_nodes(LeftNodes, RightNodes) ->
    lists:reverse(order_as_impl(LeftNodes, RightNodes, [])).
order_as_impl([], _, ONodes) ->
    ONodes;
order_as_impl([NextL|RestL], [NextR|RestR], ONodes) ->
    case NextL#sn.name == NextR#sn.name of
        true ->
            order_as_impl(RestL, RestR, [NextR|ONodes]);
        false ->
            [ONextR] = lists:filter(fun(N) -> N#sn.name == NextL#sn.name end, RestR),
            order_as_impl(RestL, [NextR|lists:delete(ONextR, RestR)], [ONextR|ONodes])
    end.

rel_path_to_string(RelPath) ->
    string:join(lists:map(fun(E) -> jsondump:kw2str(E#sn.name) end,
                          lists:filter(fun(E) ->
                                               not lists:member(E#sn.kind, ['choice', 'case'])
                                       end, lists:reverse(RelPath))), "/").

path_to_string(Path, KeepNS) ->
    if length(Path) == 0 ->
            "/";
       true ->
            Prefix = case KeepNS of
                         true -> io_lib:format("/{~s}", [(lists:last(Path))#sn.module#module.namespace]);
                         false -> "/"
                     end,
            [Node|_] = Path,
            PathStr = [Prefix|rel_path_to_string(Path)],
            case Node#sn.kind of
                'choice' ->
                    PathStr ++ io_lib:format("#~s", [jsondump:kw2str(Node#sn.name)]);
                'case' ->
                    [_|[Choice|_]] = Path,
                    PathStr ++ io_lib:format("#~s:~s", [Choice#sn.name, jsondump:kw2str(Node#sn.name)]);
                _ ->
                    PathStr
            end
    end.
