%%%----------------------------------------------------------------%%%
%%% @doc Yanger JSON dump                                          %%%
%%% Outputs schema as a JSON object                                %%%
%%%----------------------------------------------------------------%%%

-module(jsondump).
-behaviour(yanger_plugin).

-export([init/1]).

-export([substmts_to_json/2, is_substmt/1, emit_sn_json/6, kw2str/1]).

-include_lib("yanger/include/yang.hrl").

init(Ctx0) ->
    Ctx1 = yanger_plugin:register_option_specs(Ctx0, option_specs()),
    _Ctx2 = yanger_plugin:register_output_format(
              Ctx1, json, _AllowErrors = false, fun emit/3).

option_specs() ->
    [{"Json output specific options:",
      [
       %% --json-main-module
       {main_module, undefined, "json-main-module", string,
        "When parsing several modules, either give main-module as last argument, or provide name of main-module using this option."},
       %% --json-line-numbers
       {inc_linenums, undefined, "json-line-numbers", {boolean, false},
        "Include line-number for each node."}
      ]
     }].

-spec emit(#yctx{}, [#module{}], io:device()) -> [].
emit(Ctx, Mods, Fd) ->
    Opts = Ctx#yctx.options,
    MainMod = proplists:get_value(main_module, Opts),
    [Mod|_OtherMods] = if MainMod /= 'undefined' ->
            lists:filter(fun(M) -> M#module.name == ?l2a(MainMod) end, Mods);
       true -> Mods
    end,

    io:format(Fd, "{~n", []),
    emit_mod(Mod, Fd, Opts),
    %% if length(OtherMods) > 0 ->
    %%      io:format(Fd, "  \"module_map\": {~n    ~s~n  }~n",
    %%                [string:join([io_lib:format("\"~s\": \"~s\"",
    %%                                            [Module#module.prefix, Module#module.namespace]) || Module <- OtherMods],
    %%                             ",\n    ")]);
    %%    true -> ok
    %% end,

    io:format(Fd, "}~n", []),
    [].

-spec emit_mod(#module{}, io:device(), []) -> done.
emit_mod(Mod, Fd, Opts) ->
    %%    io:format(Fd, "~n***~n~p :~p~n+++~n", [Mod#module.name, Mod]),
    io:format(Fd, "  \"nodes\": {~n", []),
    TopState = lists:foldl(fun(Node, State) -> emit_sn(Node, [], State, Fd, Opts) end, {[], [], maps:new()}, Mod#module.children),
    { NodeListJson, AllContexts, TypeDefs } = TopState,
    emit_all_nodes(NodeListJson, Fd),
    io:format(Fd, "  },~n", []),
    io:format(Fd, "  \"contexts\": {~n", []),
    emit_all_contexts(AllContexts, Fd),
    emit_mod_info(Mod, Fd),
    io:format(Fd, "  },~n", []),
    io:format(Fd, "  \"types\": {~n", []),
    io:format(Fd, "    ~s~n", [string:join([emit_typedef(TypeDefKey, TypeDefs) || TypeDefKey <- maps:keys(TypeDefs)], ",\n    ")]),
    io:format(Fd, "  }~n", []).

emit_all_nodes([], _) ->
    ok;
emit_all_nodes([NodeJson], Fd) ->
    io:format(Fd, "~s~n", [NodeJson]);
emit_all_nodes([NodeJson|Rest], Fd) ->
    io:format(Fd, "~s,~n", [NodeJson]),
    emit_all_nodes(Rest, Fd).

emit_all_contexts([], _) ->
    ok;
emit_all_contexts([Ctx|Rest], Fd) ->
    io:format(Fd, "~s,~n", [emit_context(Ctx)]),
    emit_all_contexts(Rest, Fd).

emit_mod_info(Mod, Fd) ->
    TopChildren = child_names(Mod#module.children),
    io:format(Fd, "    \"/\": {~n", []),
    io:format(Fd, "      \"module\": \"~s\",~n", [Mod#module.modulename]),
    io:format(Fd, "      \"namespace\": \"~s\",~n", [Mod#module.namespace]),
    io:format(Fd, "      \"prefix\": \"~s\",~n", [Mod#module.prefix]),
    emit_mod_meta(Mod, Fd),
    emit_imports(Mod, Fd),
    io:format(Fd, "      \"extensions\": {~n", []),
    DumpExt = fun({ExtName, ExtStmt}, ExtList) ->
                      [io_lib:format("        \"~s\": {~n~s~n        }", [ExtName, emit_substmts(ExtStmt, "          ")])|ExtList]
              end,
    Extensions = lists:foldl(DumpExt, [], [{Ext#extension.name, Ext#extension.stmt} || {_, Ext} <- yang:map_to_list(Mod#module.extensions), not is_builtin_ext(Ext)]),
    io:format(Fd, "~s~n      },~n", [string:join(Extensions, ",\n")]),
    io:format(Fd, "~s~n", [named_list("children", TopChildren, "      ")]),
    io:format(Fd, "    }~n", []).

emit_imports(Mod, Fd) ->
    io:format(Fd, "      \"imports\": {~n", []),
    Imports = case Mod#module.imports of
                  [] ->
                      [];
                  [F|_] when tuple_size(F) == 3 ->
                      [{ModuleName, Prefix} || {ModuleName , _, Prefix} <- Mod#module.imports];
                  [F|_] when tuple_size(F) == 4 ->
                      [{ModuleName, Prefix} || {ModuleName , _, Prefix, _} <- Mod#module.imports]
              end,
    ImportsJson =
        [io_lib:format("\"~s\": \"~s\"", [?a2l(Prefix), ?a2l(ModuleName)]) || {ModuleName, Prefix} <- Imports],
    io:format(Fd, "        ~s~n      },~n", [string:join(ImportsJson, ",\n        ")]).

emit_mod_meta(Mod, Fd) ->
    ModMetaStmt = yang:search_one_substmt({'cliparser-extensions-v11', 'module-meta-data'}, Mod#module.stmt),
    case ModMetaStmt of
       false ->
           io:format(Fd, "      \"module_meta\": [],~n", []);
       {_, _, _, SubStmts} -> io:format(Fd, "      \"module_meta\":~n~s,~n", [substmts_to_json(SubStmts, "      ")])
    end.

is_builtin_ext(Ext) ->
    case yang:search_one_substmt({'cliparser-extensions-v11', 'builtin'}, Ext#extension.stmt) of
        false -> false;
        _ -> true
    end.

emit_context({Path, Node, MatchChildren}) ->
    ModeChildren = lists:filter(fun(Child) -> not lists:member(Child, MatchChildren) end, child_names(Node#sn.children)),
    io_lib:format("    \"~s\": {~n", [path_to_string(Path)]) ++
        io_lib:format("~s~n", [named_list("children", ModeChildren, "      ")]) ++
        io_lib:format("    }", []).

emit_typedef({TypeMod, TypeName}, TypeDefs) ->
    Type = (maps:get({TypeMod, TypeName}, TypeDefs))#typedef.type,
    { NewTypeDefs, JsonType } = emit_type(Type, maps:new(), "    "),
    ThisTypeDef = io_lib:format("\"~s:~s\": ~s", [TypeMod, TypeName, JsonType]),
    case (maps:size(NewTypeDefs) > 0) of
        true ->
            ThisTypeDef ++ ",\n    " ++ [string:join([emit_typedef(TypeDefKey, NewTypeDefs) || TypeDefKey <- maps:keys(NewTypeDefs)], ",\n    ")];
        false -> ThisTypeDef
    end.

-spec emit_sn(#sn{}, [#sn{}], {list(), list(), map()}, io:device(), []) -> { list(), list(), map()}.
emit_sn(Node, ParentPath, State, Fd, Opts) ->
    {NodeListJson, Contexts, TypeDefs} = State,
    case Node#sn.kind of
        'choice' ->
            Path = ParentPath ++ [Node],
            PathStr = path_to_string(ParentPath) ++ io_lib:format("#~s", [kw2str(Node#sn.name)]);
        'case' ->
            Path = lists:sublist(ParentPath, length(ParentPath) - 1),
            PathStr = path_to_string(Path) ++
                io_lib:format("#~s:~s", [kw2str((lists:last(ParentPath))#sn.name), kw2str(Node#sn.name)]);
        _ ->
            Path = ParentPath ++ [Node],
            PathStr = path_to_string(Path)
    end,
    CaseExtras =
        if (Node#sn.kind == 'case') ->
                GrandParent = lists:nth(length(ParentPath)-1, ParentPath),
                case has_tailf('cli-sequence-commands', GrandParent) of
                    true -> io_lib:format("      \"in_sequence\": \"true\",~n", []);
                    false -> ""
                end ++
                case (has_tailf('cli-compact-syntax', GrandParent) orelse
                      has_tailf('cli-flatten-container', GrandParent) orelse
                      (is_mode(GrandParent) andalso hide_in_submode(Node))) of
                    true -> io_lib:format("      \"in_compact\": \"true\",~n", []);
                    false -> ""
                end;
            true -> ""
        end,
    { NodeJson, NewTypeDefs, Children } = emit_sn_json(Node, PathStr, TypeDefs, CaseExtras,
                                                      fun({Kw, _, _, _}) -> is_substmt(Kw) end, Opts),
    case is_mode(Node) of
        true -> NewContexts = [{Path, Node, Children}|Contexts];
        false -> NewContexts = Contexts
    end,
    case ParentPath of
        [] -> NewState = {[NodeJson|NodeListJson], NewContexts, NewTypeDefs};
        _ -> NewState = {NodeListJson, NewContexts, NewTypeDefs},
             io:format(Fd, "~s,~n", [NodeJson]) % flush all nodes below top immediately to avoid big heap
    end,
    lists:foldl(fun(Child, NextState) -> emit_sn(Child, Path, NextState, Fd, Opts) end, NewState, Node#sn.children).

emit_sn_json(Node, PathStr, TypeDefs, Extras0, SubsFilterFn, Opts) ->
    Extras1 = Extras0 ++
        if length(Node#sn.augmented_by) > 0 ->
                emit_augments(Node);
           true -> ""
        end,
    SubStmtsJson = emit_substmts(Node, "      ", SubsFilterFn),
    IncLineNum = proplists:get_value(inc_linenums, Opts),
    NodeJson = io_lib:format("    \"~s\": {~n", [PathStr]) ++
        io_lib:format("      \"keyword\": \"~s\",~n", [Node#sn.kind]) ++
        if IncLineNum ->
                io_lib:format("      \"line\": \"~p\",~n", [yangdiff:stmt2line(Node#sn.stmt)]);
           true -> ""
        end ++
        if length(SubStmtsJson) > 0 ->
                io_lib:format("~s,~n", [SubStmtsJson]);
           true -> ""
        end ++
        if Node#sn.kind == list
           -> io_lib:format("~s,~n", [named_list("keys", Node#sn.keys, "      ")]);
           true -> ""
        end ++
        Extras1 ++
        case lists:member(Node#sn.kind, [leaf, 'leaf-list']) of
            true ->
                Children = [],
                { NewTypeDefs, JsonType } = emit_type(Node#sn.type, TypeDefs, "      "),
                io_lib:format("      \"type\": ~s", [JsonType]);
            false ->
                Children = match_children(Node),
                NewTypeDefs = TypeDefs,
                named_list("children", Children, "      ")
        end ++
        io_lib:format("~n    }", []),
    { NodeJson, NewTypeDefs, Children }.

emit_augments(Node) ->
    AugmentsFrom0 =
        sets:to_list(lists:foldl(fun(Aug, NSAndPrefSet) ->
                                         sets:union(NSAndPrefSet,
                                                    sets:from_list([{C#sn.module#module.namespace, C#sn.module#module.name} || C <- Aug#augment.children]))
                                 end,
                                 sets:new(), Node#sn.augmented_by)),
    AugmentsFrom1 = lists:filter(fun({ NS, _ }) ->
                                         NS /= Node#sn.module#module.namespace
                                 end,
                                 AugmentsFrom0),
    if length(AugmentsFrom1) > 0 ->
            io_lib:format("      \"augmented_from\": {~n        ~s~n      },~n",
                          [string:join([io_lib:format("\"~s\": \"~s\"", [Name, NS]) ||
                                           { NS, Name } <- AugmentsFrom1], ",\n        ")]);
       true -> ""
    end.

emit_type(Type, TypeDefs, _) when is_record(Type#type.base, typedef) ->
    TypeDef = Type#type.base,
    TypeName = TypeDef#typedef.name,
    { TypeMod, _ } = TypeDef#typedef.moduleref,
    { maps:put({TypeMod, TypeName}, TypeDef, TypeDefs), io_lib:format("\"#~s:~s\"", [TypeMod, TypeName]) };

emit_type(Type, TypeDefs, Indent) when Type#type.base == 'union' ->
    Types = (Type#type.type_spec)#union_type_spec.types,
    NextIndent = Indent ++ "  ",
    UnionFn = fun(NextType, { NextTypeDefs, JsonTypes } ) ->
                      { NewTypeDefs, JsonType } = emit_type(NextType, NextTypeDefs, NextIndent),
                      { NewTypeDefs, [JsonType|JsonTypes] }
              end,
    { FinalTypeDefs, RevJsonTypes } = lists:foldl(UnionFn, { TypeDefs, [] }, Types),
    LineSep = io_lib:format(",~n~s", [NextIndent]),
    FinalJsonTypes = lists:reverse(RevJsonTypes),
    { FinalTypeDefs, io_lib:format("[~n~s~s~n~s]", [NextIndent, string:join(FinalJsonTypes, LineSep), Indent]) };

emit_type(Type, TypeDefs, Indent) when is_record(Type#type.type_spec, integer_type_spec),
                                       length((Type#type.type_spec)#integer_type_spec.range) > 1 ->
    Min = (Type#type.type_spec)#integer_type_spec.min,
    Max = (Type#type.type_spec)#integer_type_spec.max,
    Range = (Type#type.type_spec)#integer_type_spec.range,
    RangeStmt = (Type#type.type_spec)#integer_type_spec.range_stmt,
    Union = #type{base='union',
                  type_spec=#union_type_spec{
                               types = [#type{base = Type#type.base,
                                              type_spec=#integer_type_spec{min=Min, max=Max, range=[R], range_stmt=RangeStmt}} || R <- Range]}
                 },
    emit_type(Union, TypeDefs, Indent);

emit_type(Type, TypeDefs, Indent) when not is_record(Type#type.base, typedef) ->
    { TypeDefs, emit_type_spec(Type, Type#type.type_spec, Indent) }.

emit_type_spec(Type, #integer_type_spec{range=Range}, _) ->
    TrueRange = case (Type#type.type_spec)#integer_type_spec.range_stmt == 'undefined' of
                    true -> [];
                    _ -> Range
                end,
    case TrueRange of
        [] -> io_lib:format("\"~s\"", [Type#type.base]);
        [{Lo, Hi}] ->  io_lib:format("\"~sr~p..~p\"", [Type#type.base, Lo, Hi]);
        [V] -> io_lib:format("\"~sr~p\"", [Type#type.base, V])
    end;

emit_type_spec(_, #string_type_spec{min = Min, max = Max, patterns = AllPatterns}, Indent) ->
    TypeName =
        case {Min, Max} of
            {0, infinity} -> "string";
            _ -> io_lib:format("string~p..~p", [Min, Max])
        end,
    Patterns = [?b2l(Regexp) || { _, Regexp, _ } <- lists:filter(fun({ _, _, InvMatch }) -> not InvMatch end, AllPatterns) ],
    InvPatterns = [?b2l(Regexp) || { _, Regexp, _ } <- lists:filter(fun({ _, _, InvMatch }) -> InvMatch end, AllPatterns) ],
    case length(Patterns) > 0 of
        true ->  emit_pattern_type(TypeName, Patterns, InvPatterns, Indent);
        false -> io_lib:format("\"~s\"", [TypeName])
    end;

emit_type_spec(_, #binary_type_spec{min = Min, max = Max}, _Indent) ->
    TypeName =
        case {Min, Max} of
            {0, infinity} -> "binary";
            _ -> io_lib:format("binary~p..~p", [Min, Max])
        end,
    io_lib:format("\"~s\"", [TypeName]);

emit_type_spec(_, #enumeration_type_spec{enums = Enums}, Indent) ->
    TokenStr = named_list("tokens", [Token || { Token, _ } <- Enums], Indent ++ "  "),
    Ordinals = [ Val || { _, Val } <- Enums],
    ValStr = case is_normal_ordinals(Ordinals) of
                 true -> "";
                 false -> named_list("values", Ordinals, Indent ++ "  ") ++ ",\n"
             end,
    io_lib:format("{~n~s  \"typename\": \"enumeration\",~n~s~s~n~s}", [Indent, ValStr, TokenStr, Indent]);

emit_type_spec(Type, #leafref_type_spec{}, _) ->
    Path = yang:stmt_arg(yang:search_one_substmt('path', Type#type.stmt)),
    io_lib:format("\"leafref<~s>\"", [Path]);

emit_type_spec(_, #decimal64_type_spec{ fraction_digits = FractDigits , min = _Min, max = _Max }, Indent) ->
    Pattern = io_lib:format("[+\\-]?[0-9]+(?:\\.[0-9]{0,~B})?", [FractDigits]),
    emit_pattern_type("decimal64", [Pattern], Indent);

emit_type_spec(_, #empty_type_spec{}, _) ->
    "\"empty\"";

emit_type_spec(_, #boolean_type_spec{}, _) ->
    "\"boolean\"".

emit_pattern_type(TypeName, Patterns, Indent) ->
    emit_pattern_type(TypeName, Patterns, [], Indent).

emit_pattern_type(TypeName, Patterns, InvPatterns, Indent) ->
    LineSep = io_lib:format(",~n    ~s", [Indent]),
    EscPatterns = lists:map(fun(Pat) -> to_str(Pat) end, Patterns),
    PatternsStr = string:join([io_lib:format("\"~s\"", [Regexp]) || Regexp <- EscPatterns], LineSep),
    if length(InvPatterns) > 0 ->
            EscInvPatterns = lists:map(fun(Pat) -> to_str(Pat) end, InvPatterns),
            InvPatternsStr = string:join([io_lib:format("\"~s\"", [Regexp]) || Regexp <- EscInvPatterns], LineSep),
            io_lib:format("{~n~s  \"typename\": \"~s\",~n~s  \"patterns\": [~n~s    ~s~n~s  ],~n~s  \"invpatterns\": [~n~s    ~s~n~s  ]~n~s}", [Indent, TypeName, Indent, Indent, PatternsStr, Indent, Indent, Indent, InvPatternsStr, Indent, Indent]);
       true ->
            io_lib:format("{~n~s  \"typename\": \"~s\",~n~s  \"patterns\": [~n~s    ~s~n~s  ]~n~s}", [Indent, TypeName, Indent, Indent, PatternsStr, Indent, Indent])
    end.

match_children(Node) ->
    KeyChildren = case Node#sn.kind of
                      container -> [];
                      list -> key_children(Node);
                      _ -> []
                  end,
    KeyChildren ++ case is_mode(Node) of
                       true -> submode_children(Node, KeyChildren);
                       false -> nonsubmode_children(Node, KeyChildren)
                   end.

submode_children(Node, KeyChildren) ->
    FilterFn = fun(Child) ->
                       (not_is_member(Child, KeyChildren) andalso
                        hide_in_submode(Child))
               end,
    child_names(lists:filter(FilterFn, Node#sn.children)).

nonsubmode_children(Node, KeyChildren) ->
    FilterFn = fun(Child) ->
                       not_is_member(Child, KeyChildren)
               end,
    child_names(lists:filter(FilterFn, Node#sn.children)).

not_is_member(Node, Nodes) ->
    Name = node_name(Node),
    (not lists:member(Name, Nodes)).

hide_in_submode(Node) ->
    case Node#sn.kind of
        'choice' -> lists:any(fun(Child) -> hide_in_submode(Child) end, Node#sn.children);
        'case' -> lists:any(fun(Child) -> hide_in_submode(Child) end, Node#sn.children);
        _ -> has_tailf('cli-hide-in-submode', Node)
    end.

key_children(Node) ->
    PrefKeysWithIdx = lists:filter(fun({ _, Idx }) -> Idx > 0 end,
                                   lists:map(fun(Child) ->
                                                     Name = node_name(Child),
                                                     { Name, pref_key_idx(Child) } end, Node#sn.children)),
    SortPrefKeys = lists:sort(fun({ _, LIdx}, { _, RIdx}) -> LIdx =< RIdx end, PrefKeysWithIdx),
    key_children_impl(Node#sn.keys, SortPrefKeys, [], 1).

node_name(Node) ->
    Name = case Node#sn.kind of
               'choice' -> ?l2a(lists:flatten(io_lib:format("#~s", [kw2str(Node#sn.name)])));
               _ -> Node#sn.name
           end,
    Name.

key_children_impl(Keys, [], SortedKeys, _) ->
    SortedKeys ++ Keys;

key_children_impl(Keys, [{NextPK, N}|RestPrefKeys], SortedKeys, N) ->
    key_children_impl(Keys, RestPrefKeys, SortedKeys ++ [NextPK], N);

key_children_impl([NextKey|RestKeys], PrefKeys, SortedKeys, N) ->
    key_children_impl(RestKeys, PrefKeys, SortedKeys ++ [NextKey], N+1).

pref_key_idx(Node) ->
    case Node#sn.kind of
        Kind when (Kind == 'choice') orelse (Kind == 'case') ->
            if Node#sn.children == [] ->
                    0;
               true ->
                    [First|_] = Node#sn.children,
                    pref_key_idx(First) %% Assume valid model (i.e. if prefix-keys in choice, must be same prefix, otherwise hard to use)
               end;
        _ ->
            PrefixKeyStmt = yang:search_one_substmt({'tailf-common', 'cli-prefix-key'}, Node#sn.stmt),
            case PrefixKeyStmt of
                false -> 0;
                _ ->
                    PrefKeyBefore = yang:search_one_substmt({'tailf-common', 'cli-before-key'},
                                                            PrefixKeyStmt),
                    case PrefKeyBefore of
                        false -> 1;
                        _ -> yang:stmt_arg(PrefKeyBefore)
                    end
            end
    end.

is_mode(Node) ->
    case Node#sn.kind of
        list -> not has_tailf('cli-suppress-mode', Node);
        container -> has_tailf('cli-add-mode', Node);
        _ -> false
    end.

has_tailf(Annotation, Node) ->
    {_, _, _, SubStmts} = Node#sn.stmt,
    CheckFn = fun({Kw, _, _, _}) ->
                      case Kw of
                          { 'tailf-common', Annotation } -> true;
                          _ -> false
                      end
              end,
    lists:any(CheckFn, SubStmts).

named_list(Name, Values, Indent) ->
    io_lib:format("~s\"~s\": [~s]", [Indent, Name, join_names(Values, ",")]).

child_names(Children) ->
    NameFn = fun(Sn) ->
                     case Sn#sn.kind of
                         choice -> ?l2a(lists:flatten(io_lib:format("#~s", [kw2str(Sn#sn.name)])));
                         _ -> Sn#sn.name
                     end
             end,
    lists:map(NameFn, Children).

path_to_string(Path) ->
    ["/"|string:join(lists:map(fun(E) -> kw2str(E#sn.name) end, Path), "/")].

kw2str(Keyword) when is_atom(Keyword) ->
    ?a2l(Keyword);
kw2str({ Mod, Name }) ->
    io_lib:format("~s:~s", [Mod, Name]).

join_names(Names, Sep) ->
    string:join(lists:map(fun(E) -> io_lib:format("\"~s\"", [to_str(E)]) end, Names), Sep).

emit_substmts(Node, Indent) ->
    emit_substmts(Node, Indent,
                  fun({Kw, _, _, _}) -> is_substmt(Kw) end).

emit_substmts(Node, Indent, SubsFilterFn) when is_record(Node, sn) ->
    {_, _, _, SubStmts} = Node#sn.stmt,
    SubStmtsIncUsesWhen = SubStmts ++ get_uses_when(Node#sn.'when'),
    emit_substmts({[], [], 'undefined', SubStmtsIncUsesWhen}, Indent, SubsFilterFn);
emit_substmts({_, _, _, Subs}, Indent, SubsFilterFn) ->
    SubsFiltered = lists:filter(SubsFilterFn, Subs),
    case length(SubsFiltered) of
        0 -> "";
        _ -> io_lib:format("~s\"substmts\":~n~s", [Indent, substmts_to_json(SubsFiltered, Indent)])
    end.

get_uses_when([]) ->
    [];
get_uses_when([When|Rest]) ->
    case When of
        %% NSO 4.x
        { _ , 'uses', { 'when', Arg, Pos, SubStmts } } ->
            [{ 'uses-when', Arg, Pos, SubStmts }|get_uses_when(Rest)];
        %% NSO 5.x
        { _ , _, 'uses', { 'when', Arg, Pos, SubStmts } } ->
            [{ 'uses-when', Arg, Pos, SubStmts }|get_uses_when(Rest)];
        _  -> get_uses_when(Rest)
    end.

substmts_to_json([], _) ->
    "";
substmts_to_json(SubStmts, Indent) ->
    io_lib:format("~s[~n~s~n~s]", [Indent, substmts_to_json_impl(SubStmts, Indent ++ "  "), Indent]).

substmts_to_json_impl([], _) ->
    "";
substmts_to_json_impl([Stmt|Rest], Indent) ->
    Json = stmt_to_json(Stmt, Indent),
    case Rest of
        [] -> Json;
        _ -> Json ++ ",\n" ++ substmts_to_json_impl(Rest, Indent)
    end.

stmt_to_json({Kw, Arg, _Pos, []}, Indent) ->
    stmt_head_to_json(Kw, Arg, Indent) ++ " ]";

stmt_to_json({Kw, Arg, _Pos, SubStmts}, Indent) ->
    Body = substmts_to_json(SubStmts, Indent ++ "  "),
    case length(Body) > 0 of
        true -> stmt_head_to_json(Kw, Arg, Indent) ++ ",\n" ++ Body ++ "\n" ++ Indent ++ "]";
        false -> stmt_head_to_json(Kw, Arg, Indent) ++ "\n" ++ Indent ++ "]"
    end.

is_substmt(Kw) ->
    not lists:member(Kw, ['leaf', 'leaf-list', 'container', 'list', 'key', 'choice', 'case', 'type', 'grouping']).

stmt_head_to_json(Kw, [], Indent) ->
    io_lib:format("~s[ \"~s\"", [Indent, to_str(Kw)]);
stmt_head_to_json(Kw, Arg, Indent) ->
    io_lib:format("~s[ \"~s\",~n~s\"~s\"", [Indent, to_str(Kw), Indent ++ "  ", to_str(Arg)]).

to_str(Arg) ->
    EscStr = fun(Str) ->
                     lists:map(fun(C) ->
                                       case C of
                                           $\" -> "\\\"";
                                           $\\ -> "\\\\";
                                           $\n -> "\\n";
                                           $\t -> "\\t";
                                           _ -> C
                                       end
                               end, Str)
             end,
    case Arg of
        [] -> "";
        {Module, Name} -> io_lib:format("~s:~s", [Module, Name]);
        ArgBin when is_binary(ArgBin) -> EscStr(?b2l(ArgBin));
        ArgAtom when is_atom(ArgAtom) -> ?a2l(ArgAtom);
        ArgInt when is_integer(ArgInt) -> integer_to_list(ArgInt);
        _ ->
            EscStr(Arg)
    end.

is_normal_ordinals([0]) ->
    true;
is_normal_ordinals([0|Rest]) ->
    chk_normal_ordinals(0, Rest);
is_normal_ordinals(_) ->
    false.

chk_normal_ordinals(_, []) ->
    true;
chk_normal_ordinals(N, [Next|Rest]) ->
    case Next == N + 1 of
        true ->
            chk_normal_ordinals(Next, Rest);
        false ->
            false
    end;
chk_normal_ordinals(_, _) ->
    false.
