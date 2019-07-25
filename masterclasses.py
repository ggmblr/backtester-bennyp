from utilities.filehandler import FileHandler
from utilities.graphing import *
from settings import BACKTEST_CURRENCIES as UNIVERSE
import typing
from dataclasses import dataclass
from tqdm import tqdm

'''
Declaring Global Scope Data Types (really just named tuples),
but here in python, we don't really have a 'typedef' equivalent
'''

signal_tuple = typing.NamedTuple('signal_2',
                             [('action', str),
                              ('signal_str', float),
                              ('currency', str),
                              ('price', float),
                              ('quantity', float)])


generated_data = typing.NamedTuple('rdata',
                                   [('price_data', dict),
                                    ('equity_history', list),
                                    ('signal_data', dict)])


class Account:
    equity = 0
    cash = 0
    '''
    equity = cash + market value of all active holdings
    quantity = amount in native currency (eth, btc, etc...)
    mkt_value = quantity's worth in USD at a given time
    cash = cash, in USD
    holdings = dict of currency and the amount of that currency in native terms
    '''

    holdings = {}
    market_values = {}

    def __init__(self):
        self.initial_capital = 1000
        Account.equity = self.initial_capital
        Account.cash = Account.equity

        for c in UNIVERSE:
            Account.holdings.update({c: 0})
            Account.market_values.update({c: 0})

    @staticmethod
    def update_market_value(signal):
        Account.market_values.update(
            {signal.currency: signal.price * Account.holdings[signal.currency]})

    @staticmethod
    def update_account_equity():
        sum_mkt = 0
        for v in Account.market_values.values():
            sum_mkt += v

        Account.equity = Account.cash + sum_mkt


class RiskModel:
    position_sizing = .5

    @staticmethod
    def get_position_size(signal_strength: float, action: str) -> float:
        # return signal_strength * (RiskModel.position_sizing * Account.equity)
        if action == 'buy' or action == 'sell':
            return 5  # FUCK YOU MR. FUNCTION
        else:
            return 0


class ExecutionModel:

    @staticmethod
    def debug(signal: signal_tuple):
        if signal.action == 'buy':
            q1 = Account.holdings.get(signal.currency)
            q2 = signal.quantity
            print('bought {} {} at {}. Total: '
                  '{} -> Quantity of {}: {} --> {}'
                  .format(signal.quantity, signal.currency, signal.price,
                          signal.price * signal.quantity, signal.currency,
                          q1, q1 + q2))
        if signal.action == 'sell':
            q1 = Account.holdings.get(signal.currency)
            tq = q1 - signal.quantity if signal.quantity < q1 else q1
            print('sold {} {} at {}. Total: '
                  '{} -> Quantity of {}: {} --> {}'
                  .format(signal.quantity, signal.currency, signal.price,
                          signal.price * signal.quantity, signal.currency,
                          q1, q1 - tq))

    @staticmethod
    def limit_buy(price, currency, time_limit):
        pass

    @staticmethod
    def limit_sell(price, currency, time_limit):
        pass

    @staticmethod
    def backtest_buy(signal: signal_tuple):
        q1 = Account.holdings.get(signal.currency)
        q2 = signal.quantity
        # ExecutionModel.debug(signal)
        Account.holdings[signal.currency] = q1 + q2
        Account.cash -= q2 * signal.price

    @staticmethod
    def backtest_sell(signal: signal_tuple):
        q1 = Account.holdings.get(signal.currency)
        q2 = signal.quantity
        tq = q1 - q2 if q2 < q1 else q1
        # ExecutionModel.debug(signal)
        Account.holdings[signal.currency] = q1 - tq
        Account.cash += tq * signal.price


class Algorithm:
    # index here just means date
    def backtest_action(self, short_sma, long_sma, currency):
        raise NotImplementedError

    def action(self):
        raise NotImplementedError


class BacktestModel:

    @dataclass
    class BacktestStats:
        """
        This class ought to be instantiated prior to the calling
        of any function where the following class variables would
        have been passed to the function as params individually
        """
        price_data: dict  # dict of lists
        signal_data: dict  # dict of lists
        equity_history: pd.DataFrame  # dataframe
        backtest_stats: dict  # non-nested dict: e.g. {str: int}

        def get_signal_list(self, currency: str) -> list:
            return self.signal_data.get(currency)

        def get_price_dataframe(self, currency: str) -> pd.DataFrame:
            return self.price_data.get(currency)

    def __init__(self, algorithm):
        self.algorithm = algorithm

    @staticmethod
    def update_quantity(signal):
        # feeds signal into risk model to get position sizing
        signal.update({'quantity': RiskModel.get_position_size(signal.signal_str)})

    @staticmethod
    def execute_signal(signal: signal_tuple):
        if signal.action == 'buy':
            ExecutionModel.backtest_buy(signal)
        elif signal.action == 'sell':
            ExecutionModel.backtest_sell(signal)

    def gen_backtest(self, universe: list) -> generated_data:

        currencies = universe
        data_dict = {}
        sig_dict = {}
        equity_history = []
        data = None

        for c in currencies:
            data = pd.DataFrame(FileHandler.read_from_file(FileHandler.get_filestring(c)))
            data_dict.update({c: data})
            sig_dict.update({c: []})

        print('generating backtest values...')
        for idx in tqdm(range(len(data))):
            for c in currencies:
                sma20_series = Technicals.pandas_sma(20, data_dict[c])
                sma50_series = Technicals.pandas_sma(50, data_dict[c])
                sma20 = float(sma20_series[idx])
                sma50 = float(sma50_series[idx])
                response = self.algorithm.backtest_action(short_sma=sma20,
                                                          long_sma=sma50,
                                                          currency=c)
                q = RiskModel.get_position_size(response['signal_str'], response['action'])
                signal = signal_tuple(action=response['action'],
                                      signal_str=response['signal_str'],
                                      currency=c,
                                      price=float(data_dict[c].at[idx, 'close']),
                                      quantity=q)

                self.execute_signal(signal)
                Account.update_market_value(signal)
                Account.update_account_equity()
                sig_dict.get(c).append(signal)
            equity = Account.equity
            equity_history.append(equity)

        return generated_data(price_data=data_dict,
                              equity_history=equity_history,
                              signal_data=sig_dict)

    def calc_backtest(self, gd: generated_data) -> BacktestStats:
        dd_stats = Technicals.calc_drawdown(gd.equity_history)

        profit = round(gd.equity_history[-1] - gd.equity_history[0], 2)

        backtest_stats = {
            'initial equity': '${}'.format(gd.equity_history[0]),
            'profit': '${}'.format(profit),
            'return': '{}%'.format(round(100 * (profit / gd.equity_history[0]), 2)),
            'max. drawdown': '{}%'.format(round(dd_stats['ddp'], 2)),
            'longest drawdown': '{} candles'.format(dd_stats['ddl']),
            'gmax_idx': dd_stats['gmax_idx'],
            'gmin_idx': dd_stats['gmin_idx'],
        }
        return self.BacktestStats(price_data=gd.price_data,
                                  signal_data=gd.signal_data,
                                  equity_history=pd.DataFrame(gd.equity_history),
                                  backtest_stats=backtest_stats)

    def visualize_backtest(self, currency):

        gd = self.gen_backtest(UNIVERSE)
        bs = self.calc_backtest(gd)

        moving_average_full_graph(currency, bs)
