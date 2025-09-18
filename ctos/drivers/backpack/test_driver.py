from ast import main
from numpy import allclose
from driver import *
from util import rate_price2order, align_decimal_places, round_to_two_digits, cal_amount, json
import time


if __name__ == '__main__':
    bp = BackpackDriver()
    print(bp.get_price_now('ETH_USDC_PERP'))


    # order_id, err  = bp.place_order('ETH_USDC_PERP', 'bid', 'limit', 0.1, 4500.1)

    # print(order_id, err)
    # print(bp.fees())
    # print(bp.fetch_balance())
    # print(bp.get_open_orders())
    # order_id, err = bp.amend_order(order_id=order_id, symbol='ETH_USDC_PERP', price=4488)
    # print(bp.get_order_status(symbol='ETH_USDC_PERP', order_id=order_id))

    # print(bp.revoke_order(order_id=order_id, symbol='ETH_USDC_PERP'))
    pos, _ = bp.get_position()
    print(json.dumps(pos, indent=4))

    now_position = {x['symbol']:float(x['netCost']) for x in pos}
    print(now_position)

    all_coins, _  = bp.symbols()
    print(all_coins)

    all_coins = [x[:x.find('_')].lower() for x in all_coins if x[:x.find('_')].lower() in rate_price2order.keys()]
    print(all_coins, len(all_coins))


    # while True:
    #     time.sleep(3)

    with open('good_group.txt', 'r', encoding='utf8') as f:
        data = f.readlines()
        good_group = data[0].strip().split(',')
        all_rate = [float(x) for x in data[1].strip().split(',')]
        btc_rate = all_rate[0] / sum(all_rate)
        split_rate = {good_group[x + 1]: all_rate[x + 1] / sum(all_rate) for x in range(len(all_rate) - 1)}


    init_operate_position = bp.fetch_balance() * 0.15
    new_rate_place2order = {k:v for k,v in rate_price2order.items() if k in all_coins}

    usdt_amounts = []
    coins_to_deal = []
    is_btc_failed = False
    now_position = {}
    for coin in all_coins:
        time.sleep(0.2)
        if coin in good_group:
            operate_amount = cal_amount(coin, init_operate_position, good_group, btc_rate, split_rate)
            if is_btc_failed:
                operate_amount = -operate_amount
            if bp._norm_symbol(coin)[0] in now_position:
                operate_amount = operate_amount - now_position[bp._norm_symbol(coin)[0]]
            usdt_amounts.append(operate_amount)
            coins_to_deal.append(coin)
        else:
            sell_amount = init_operate_position / (len(new_rate_place2order) - len(good_group))
            if is_btc_failed:
                sell_amount = -sell_amount
            sell_amount = -sell_amount
            if bp._norm_symbol(coin)[0] in now_position:
                sell_amount = sell_amount - now_position[bp._norm_symbol(coin)[0]]
            usdt_amounts.append(sell_amount)
            coins_to_deal.append(coin)

    for idx in range(len(coins_to_deal)):
        usdt = usdt_amounts[idx]
        coin = coins_to_deal[idx]
        price = bp.get_price_now(coin)
        if usdt < 0:
            sell_price = align_decimal_places(price, price * 1.001)
            sell_quan = round_to_two_digits(usdt / sell_price)
            print(sell_price, sell_quan)
            print(coin, 'sell', 'Limit', sell_price, abs(sell_quan), usdt)
            # continue
            order_id , err = bp.place_order(coin, 'sell', 'Limit', price=sell_price, size=abs(sell_quan))
            if err:
                print(err, sell_price, sell_quan, coin)

        elif usdt > 0:
            buy_price = align_decimal_places(price, price * 0.999)
            buy_quan = round_to_two_digits(usdt / buy_price)
            print(buy_price, buy_quan)
            print(coin, 'buy', 'Limit', buy_price, abs(buy_quan), usdt)
            # continue
            order_id , err = bp.place_order(coin, 'buy', 'Limit', price=buy_price, size=abs(buy_quan))
            if err:
                print(err, sell_price, sell_quan, coin)
            else:
                print(order_id, coin)
