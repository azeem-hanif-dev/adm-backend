# Create a debug script to check the specific customers
import asyncio
from db import customers_coll

async def check_customer_data():
    emails = ["tanzeel@rehman.nl", "htanzeel04@gmail.com"]
    
    for email in emails:
        customer = await customers_coll.find_one({"email": email})
        if customer:
            print(f"\nCustomer: {email}")
            print(f"  Name: {customer.get('name')}")
            print(f"  Country: {customer.get('country')}")
            print(f"  Country type: {type(customer.get('country'))}")
            print(f"  Full document: {customer}")
        else:
            print(f"\nCustomer {email} not found")

if __name__ == "__main__":
    asyncio.run(check_customer_data())