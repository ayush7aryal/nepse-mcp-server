import requests


def login_meroshare(client_id: int, username: str, password: str) -> str:
    """
    Logs into MeroShare and returns the Authorization token.
    """
    try:
        url = "https://webbackend.cdsc.com.np/api/meroShare/auth/"
        payload = {
            "clientId": client_id,
            "username": username,
            "password": password
        }
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0"
        }

        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()

        token = response.headers.get("Authorization")
        if not token:
            raise Exception("Authorization token not found in response headers")

        return token

    except Exception as e:
        raise RuntimeError(f"Failed to login to MeroShare: {e}")
def get_portfolio(token: str, demat: str, client_code: str):
    """
    Retrieves the user's portfolio using the provided authorization token.
    """
    try:
        url = "https://webbackend.cdsc.com.np/api/meroShareView/myPortfolio/"
        payload = {
            "sortBy": "script",
            "demat": [demat],
            "clientCode": client_code,
            "page": 1,
            "size": 200,
            "sortAsc": True
        }
        headers = {
            "Authorization": token,
            "Content-Type": "application/json",
            "Origin": "https://meroshare.cdsc.com.np",
            "Referer": "https://meroshare.cdsc.com.np/",
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json, text/plain, */*"
        }

        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()

        return response.json()

    except Exception as e:
        raise RuntimeError(f"Failed to fetch portfolio: {e}")
def get_buying_price(token: str, demat: str, scrip: str):
    """
    Retrieves the buying price (WACC) of a specific script for the DEMAT account.
    """
    try:
        url = "https://webbackend.cdsc.com.np/api/myPurchase/search/wacc/"
        payload = {
            "demat": demat,
            "scrip": scrip
        }
        headers = {
            "Authorization": token,
            "Content-Type": "application/json",
            "Origin": "https://meroshare.cdsc.com.np",
            "Referer": "https://meroshare.cdsc.com.np/",
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json, text/plain, */*"
        }

        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()

        return response.json()

    except Exception as e:
        raise RuntimeError(f"Failed to fetch buying price: {e}")

# def calculate_portfolio_performance(token: str, demat: str, client_code: str):
#     """
#     Calculates portfolio performance including current value, buying price, and profit/loss for each stock
#     """
#     try:
#         # Get portfolio data
#         portfolio = get_portfolio(token, demat, client_code)
        
#         if not portfolio or 'meroShareMyPortfolio' not in portfolio:
#             raise Exception("No portfolio data found")
        
#         portfolio_items = portfolio['meroShareMyPortfolio']
#         portfolio_performance = []
#         total_current_value = 0
#         total_buying_value = 0
        
#         for item in portfolio_items:
#             script = item['script']
#             current_balance = item['currentBalance']
#             current_price = float(item['lastTransactionPrice'])
            
#             # Calculate current value
#             current_value = current_balance * current_price
            
#             # Get buying price (WACC)
#             buying_data = get_buying_price(token, demat, script)
            
#             if buying_data and buying_data.get('success') and 'waccSummaryResponse' in buying_data:
#                 buying_info = buying_data['waccSummaryResponse']
#                 average_buy_rate = float(buying_info['averageBuyRate'])
#                 total_buying_cost = float(buying_info['totalCost'])
#             else:
#                 average_buy_rate = 0
#                 total_buying_cost = 0
            
#             # Calculate buying value (alternative method if WACC not available)
#             buying_value = current_balance * average_buy_rate if average_buy_rate > 0 else total_buying_cost
            
#             # Calculate profit/loss
#             profit_loss = current_value - buying_value
#             profit_loss_percent = (profit_loss / buying_value * 100) if buying_value > 0 else 0
            
#             stock_data = {
#                 'script': script,
#                 'script_name': item['scriptDesc'],
#                 'quantity': current_balance,
#                 'current_price': current_price,
#                 'current_value': current_value,
#                 'average_buy_price': average_buy_rate,
#                 'buying_value': buying_value,
#                 'profit_loss': profit_loss,
#                 'profit_loss_percent': profit_loss_percent
#             }
            
#             portfolio_performance.append(stock_data)
#             total_current_value += current_value
#             total_buying_value += buying_value
        
#         # Calculate overall performance
#         overall_profit_loss = total_current_value - total_buying_value
#         overall_profit_loss_percent = (overall_profit_loss / total_buying_value * 100) if total_buying_value > 0 else 0
        
#         return {
#             'stocks': portfolio_performance,
#             'summary': {
#                 'total_current_value': total_current_value,
#                 'total_buying_value': total_buying_value,
#                 'total_profit_loss': overall_profit_loss,
#                 'total_profit_loss_percent': overall_profit_loss_percent
#             }
#         }
        
#     except Exception as e:
#         raise RuntimeError(f"Failed to calculate portfolio performance: {e}")
def calculate_portfolio_performance(token: str, demat: str, client_code: str):
    """
    Calculates portfolio performance including current value, buying price, and profit/loss for each stock
    """
    try:
        # Get portfolio data
        portfolio = get_portfolio(token, demat, client_code)
        
        if not portfolio or 'meroShareMyPortfolio' not in portfolio:
            raise Exception("No portfolio data found")
        
        portfolio_items = portfolio['meroShareMyPortfolio']
        portfolio_performance = []
        total_current_value = 0
        total_buying_value = 0
        
        for item in portfolio_items:
            script = item['script']
            current_balance = item['currentBalance']
            current_price = float(item['lastTransactionPrice'])
            
            # Calculate current value
            current_value = current_balance * current_price
            
            # Get buying price data
            buying_data = get_buying_price(token, demat, script)
            
            average_buy_rate = 0
            total_buying_cost = 0
            total_quantity = 0
            
            if buying_data and buying_data.get('success'):
                if 'waccSummaryResponse' in buying_data and buying_data['waccSummaryResponse']:
                    # If summary data is available
                    buying_info = buying_data['waccSummaryResponse']
                    average_buy_rate = float(buying_info.get('averageBuyRate', 0))
                    total_buying_cost = float(buying_info.get('totalCost', 0))
                    total_quantity = float(buying_info.get('totalQuantity', 0))
                elif 'waccUpdateResponse' in buying_data and buying_data['waccUpdateResponse']:
                    # Calculate from transaction history if summary not available
                    transactions = buying_data['waccUpdateResponse']
                    total_cost = 0
                    total_qty = 0
                    
                    for tx in transactions:
                        try:
                            qty = float(tx['transactionQuantity'])
                            rate = float(tx['rate'])
                            total_cost += qty * rate
                            total_qty += qty
                        except (KeyError, ValueError):
                            continue
                    
                    if total_qty > 0:
                        average_buy_rate = total_cost / total_qty
                        total_buying_cost = total_cost
                        total_quantity = total_qty
            
            # Calculate buying value
            if total_quantity > 0:
                # Scale the buying cost proportionally if current balance differs from total quantity
                buying_value = (current_balance / total_quantity) * total_buying_cost
            else:
                buying_value = 0
            
            # Calculate profit/loss
            profit_loss = current_value - buying_value
            profit_loss_percent = (profit_loss / buying_value * 100) if buying_value > 0 else 0
            
            stock_data = {
                'script': script,
                'script_name': item['scriptDesc'],
                'quantity': current_balance,
                'current_price': current_price,
                'current_value': current_value,
                'average_buy_price': average_buy_rate if average_buy_rate > 0 else (buying_value / current_balance if current_balance > 0 else 0),
                'buying_value': buying_value,
                'profit_loss': profit_loss,
                'profit_loss_percent': profit_loss_percent,
                'total_buy_quantity': total_quantity,
                'total_buy_cost': total_buying_cost
            }
            
            portfolio_performance.append(stock_data)
            total_current_value += current_value
            total_buying_value += buying_value
        
        # Calculate overall performance
        overall_profit_loss = total_current_value - total_buying_value
        overall_profit_loss_percent = (overall_profit_loss / total_buying_value * 100) if total_buying_value > 0 else 0
        
        return {
            'stocks': portfolio_performance,
            'summary': {
                'total_current_value': total_current_value,
                'total_buying_value': total_buying_value,
                'total_profit_loss': overall_profit_loss,
                'total_profit_loss_percent': overall_profit_loss_percent
            }
        }
        
    except Exception as e:
        raise RuntimeError(f"Failed to calculate portfolio performance: {e}")
# Example usage
if __name__ == "__main__":
    try:
        # Login
        token = login_meroshare(client_id=146, username="00292868", password="Ayush@2025")
        
        # Calculate portfolio performance
        performance = calculate_portfolio_performance(
            token, 
            demat="1301120000292868", 
            client_code="11200"
        )
        
        # Print results
        print("\nPortfolio Performance Summary:")
        print(f"Total Current Value: {performance['summary']['total_current_value']:.2f}")
        print(f"Total Buying Value: {performance['summary']['total_buying_value']:.2f}")
        print(f"Total Profit/Loss: {performance['summary']['total_profit_loss']:.2f}")
        print(f"Total Profit/Loss (%): {performance['summary']['total_profit_loss_percent']:.2f}%")
        
        print("\nIndividual Stock Performance:")
        for stock in performance['stocks']:
            print(f"\nScript: {stock['script']} ({stock['script_name']})")
            print(f"Quantity: {stock['quantity']}")
            print(f"Current Price: {stock['current_price']:.2f}")
            print(f"Current Value: {stock['current_value']:.2f}")
            print(f"Avg Buy Price: {stock['average_buy_price']:.2f}")
            print(f"Buying Value: {stock['buying_value']:.2f}")
            print(f"Profit/Loss: {stock['profit_loss']:.2f}")
            print(f"Profit/Loss (%): {stock['profit_loss_percent']:.2f}%")
            
    except Exception as e:
        print(f"Error: {e}")