-module(ec_transform).

-behaviour(application).

%% API
-export([]).

%% Application callbacks
-export([start/0, start/2, stop/1]).

%%%===================================================================
%%% API
%%%===================================================================

start() ->
    application:start(ec_transform).

%%%===================================================================
%%% Application callbacks
%%%===================================================================

start(_StartType, _StartArgs) ->
    case ec_transform_sup:start_link() of
        {ok, Pid} ->
            {ok, Pid};
        Error ->
            Error
    end.


stop(_State) ->
    ok.

%%%===================================================================
%%% Internal functions
%%%===================================================================
