import csv
import os
import random
from datetime import datetime, timedelta, timezone

# Fix seed for reproducibility while generating realistic dynamic dates
random.seed(42)

CATEGORIES_WITH_PRODUCTS = [
    # 1. Dairy
    {
        "category": "Dairy",
        "manufacturer": "Amul India",
        "products": [
            ("DAIRY-MILK-001", "Amul Taaza Toned Milk 1L", 54.0, 56.0),
            ("DAIRY-BUTTER-002", "Amul Pasteurised Butter 500g", 270.0, 275.0),
            ("DAIRY-PANEER-003", "Mother Dairy Fresh Paneer 200g", 90.0, 95.0),
            ("DAIRY-YOGURT-004", "Epigamia Greek Yogurt Mango 85g", 50.0, 55.0),
            ("DAIRY-CHEESE-005", "Britannia Processed Cheese Slices 200g", 140.0, 145.0),
            ("DAIRY-CURD-006", "Nandini Premium Curd 500g", 35.0, 38.0),
        ]
    },
    # 2. Bakery
    {
        "category": "Bakery",
        "manufacturer": "Britannia Industries",
        "products": [
            ("BAKERY-BREAD-001", "Britannia 100% Whole Wheat Bread 400g", 45.0, 50.0),
            ("BAKERY-BREAD-002", "Harvest Gold White Bread 400g", 40.0, 42.0),
            ("BAKERY-BUN-003", "English Oven Burger Buns 4pcs", 35.0, 38.0),
            ("BAKERY-PASTRY-004", "Monginis Choco Lava Cake 75g", 40.0, 45.0),
            ("BAKERY-RUSK-005", "Parle Premium Elaichi Rusk 300g", 55.0, 60.0),
        ]
    },
    # 3. Beverages
    {
        "category": "Beverages",
        "manufacturer": "Dabur India",
        "products": [
            ("BEV-JUICE-001", "Real Fruit Power Mango Juice 1L", 110.0, 120.0),
            ("BEV-JUICE-002", "Tropicana 100% Orange Juice 1L", 130.0, 140.0),
            ("BEV-TEA-003", "Tata Tea Gold 500g", 320.0, 340.0),
            ("BEV-COFFEE-004", "Nescafe Classic Instant Coffee 100g", 310.0, 325.0),
            ("BEV-DRINK-005", "Paper Boat Aamras Juice 250ml", 35.0, 40.0),
            ("BEV-SODA-006", "Coca-Cola Original Taste 1.25L", 60.0, 65.0),
        ]
    },
    # 4. Pickles
    {
        "category": "Pickles",
        "manufacturer": "Desai Foods (Mother's Recipe)",
        "products": [
            ("PICKLE-MANGO-001", "Mother's Recipe Mango Pickle 500g", 145.0, 160.0),
            ("PICKLE-GARLIC-002", "Priya Garlic Pickle in Sesame Oil 300g", 110.0, 125.0),
            ("PICKLE-LIME-003", "Tops Spicy Lime Pickle 400g", 95.0, 105.0),
            ("PICKLE-MIXED-004", "Nilon's Mixed Vegetable Pickle 500g", 130.0, 140.0),
            ("PICKLE-CHILLI-005", "Bedekar Green Chilli Pickle 300g", 85.0, 95.0),
        ]
    },
    # 5. Sauces
    {
        "category": "Sauces",
        "manufacturer": "Hindustan Unilever",
        "products": [
            ("SAUCE-KETCHUP-001", "Kissan Fresh Tomato Ketchup 950g", 135.0, 150.0),
            ("SAUCE-SCHZ-002", "Ching's Secret Schezwan Chutney 250g", 80.0, 85.0),
            ("SAUCE-MAYO-003", "Veeba Eggless Mayonnaise 250g", 75.0, 85.0),
            ("SAUCE-SOYA-004", "Tops Dark Soy Sauce 210ml", 55.0, 60.0),
            ("SAUCE-CHILLI-005", "Heinz Sweet Chilli Sauce 300g", 160.0, 175.0),
        ]
    },
    # 6. Snacks
    {
        "category": "Snacks",
        "manufacturer": "PepsiCo India",
        "products": [
            ("SNACK-CHIPS-001", "Lay's India's Magic Masala Chips 50g", 20.0, 20.0),
            ("SNACK-KURKURE-002", "Kurkure Masala Munch 85g", 20.0, 20.0),
            ("SNACK-BHUJIA-003", "Haldiram's Nagpur Alooo Bhujia 400g", 120.0, 130.0),
            ("SNACK-NACHOS-004", "Doritos Cheese Nachos 60g", 30.0, 30.0),
            ("SNACK-NUTS-005", "Nutraj Salted Roasted Almonds 200g", 280.0, 300.0),
        ]
    },
    # 7. Biscuits
    {
        "category": "Biscuits",
        "manufacturer": "Parle Products",
        "products": [
            ("DISC-PARLEG-001", "Parle-G Gold Biscuits 1kg", 120.0, 130.0),
            ("DISC-GOODDAY-002", "Britannia Good Day Butter Cookies 600g", 140.0, 150.0),
            ("DISC-FANTASY-003", "Sunfeast Dark Fantasy Choco Fills 300g", 160.0, 175.0),
            ("DISC-OREO-004", "Oreo Chocolate Cream Biscuits 120g", 35.0, 40.0),
            ("DISC-UNIBIC-005", "Unibic Chocolate Chip Cookies 150g", 65.0, 75.0),
        ]
    },
    # 8. Canned Foods
    {
        "category": "Canned Foods",
        "manufacturer": "Del Monte India",
        "products": [
            ("CANNED-CORN-001", "Del Monte Whole Kernel Sweet Corn 400g", 85.0, 95.0),
            ("CANNED-PINE-002", "Golden Crown Pineapple Slices in Syrup 850g", 180.0, 200.0),
            ("CANNED-BEANS-003", "Heinz Baked Beans in Tomato Sauce 415g", 140.0, 150.0),
            ("CANNED-MUSHROOM-004", "Urban Platter Button Mushrooms 400g", 110.0, 120.0),
        ]
    },
    # 9. Frozen Foods
    {
        "category": "Frozen Foods",
        "manufacturer": "McCain Foods",
        "products": [
            ("FROZEN-FRIES-001", "McCain French Fries Crispy 750g", 170.0, 185.0),
            ("FROZEN-PEAS-002", "Safal Frozen Green Peas 1kg", 130.0, 145.0),
            ("FROZEN-MOMOS-003", "Prasuma Chicken Veg Momos 24pcs", 290.0, 320.0),
            ("FROZEN-NUGGETS-004", "Sumeru Crispy Chicken Nuggets 500g", 240.0, 260.0),
        ]
    },
    # 10. Instant Foods
    {
        "category": "Instant Foods",
        "manufacturer": "Nestle India",
        "products": [
            ("INST-MAGGI-001", "Nestle Maggi 2-Minute Masala Noodles 560g", 110.0, 120.0),
            ("INST-SOUP-002", "Knorr Thick Tomato Soup 53g", 50.0, 55.0),
            ("INST-PASTA-003", "Maggi Pazzta Cheese Macaroni 70g", 30.0, 35.0),
            ("INST-UPMA-004", "MTR Instant Vegetable Upma Mix 160g", 45.0, 50.0),
            ("INST-POHA-005", "Saffola FITTIFY Instant Gourmet Poha 80g", 40.0, 45.0),
        ]
    },
    # 11. Spices
    {
        "category": "Spices",
        "manufacturer": "MDH Spices",
        "products": [
            ("SPICE-GARAM-001", "Everest Royal Garam Masala 100g", 85.0, 90.0),
            ("SPICE-CHILLI-002", "MDH Deggi Mirch Powder 100g", 95.0, 100.0),
            ("SPICE-TURM-003", "Catch Pure Turmeric Powder 200g", 65.0, 70.0),
            ("SPICE-CORI-004", "Tata Sampann Coriander Powder 200g", 70.0, 75.0),
            ("SPICE-PEPPER-005", "Keya Black Pepper Grinder 50g", 160.0, 175.0),
        ]
    },
    # 12. Cereals
    {
        "category": "Cereals",
        "manufacturer": "Kellogg India",
        "products": [
            ("CER-CORN-001", "Kellogg's Corn Flakes Original 875g", 310.0, 330.0),
            ("CER-OATS-002", "Quaker Rolled Oats 1kg", 180.0, 195.0),
            ("CER-MUESLI-003", "Baggry's Crunchy Muesli Fruit & Nut 400g", 270.0, 290.0),
            ("CER-CHOCOS-004", "Kellogg's Chocos Crunchy Bites 375g", 195.0, 210.0),
        ]
    },
    # 13. Packaged Foods
    {
        "category": "Packaged Foods",
        "manufacturer": "Tata Consumer Products",
        "products": [
            ("PKG-DAL-001", "Tata Sampann Unpolished Arhar Dal 1kg", 165.0, 175.0),
            ("PKG-RICE-002", "Fortune Biryani Special Basmati Rice 1kg", 195.0, 210.0),
            ("PKG-ATTA-003", "Aashirvaad Shuddh Chakki Atta 5kg", 240.0, 260.0),
            ("PKG-OIL-004", "Fortune Kachi Ghani Mustard Oil 1L", 155.0, 165.0),
            ("PKG-SALT-005", "Tata Vacuum Evaporated Iodized Salt 1kg", 25.0, 28.0),
        ]
    },
    # 14. Juices
    {
        "category": "Juices",
        "manufacturer": "Dabur India",
        "products": [
            ("JUICE-GUAVA-001", "B-Natural Pink Guava Juice 1L", 105.0, 115.0),
            ("JUICE-COCO-002", "RAW Pressery 100% Tender Coconut Water 200ml", 60.0, 65.0),
            ("JUICE-ORANGE-003", "Minute Maid Pulpy Orange Drink 1L", 90.0, 99.0),
            ("JUICE-APPLE-004", "Real Fruit Power Himalayan Apple Juice 1L", 115.0, 125.0),
        ]
    },
    # 15. Condiments
    {
        "category": "Condiments",
        "manufacturer": "Wingreens Farms",
        "products": [
            ("COND-TABASCO-001", "Tabasco Original Red Pepper Sauce 60ml", 220.0, 240.0),
            ("COND-MUSTARD-002", "French's Classic Yellow Mustard 226g", 210.0, 230.0),
            ("COND-DIP-003", "Wingreens Farms Chipotle Dip 180g", 175.0, 190.0),
            ("COND-SRIRACHA-004", "Huy Fong Sriracha Hot Chili Sauce 255g", 320.0, 350.0),
        ]
    },
    # 16. Ready-to-eat foods
    {
        "category": "Ready-to-eat foods",
        "manufacturer": "MTR Foods",
        "products": [
            ("RTE-PANEER-001", "MTR Ready to Eat Paneer Butter Masala 300g", 140.0, 150.0),
            ("RTE-DAL-002", "Kitchens of India Dal Makhani 285g", 150.0, 165.0),
            ("RTE-RAJMA-003", "Haldiram's Minute Khana Rajma Chawal 375g", 125.0, 135.0),
            ("RTE-BIRYAN-004", "Tata Q Spicy Chicken Biryani 330g", 185.0, 199.0),
        ]
    }
]


def generate_mock_inventory_csv(output_path="data/mock_inventory.csv", target_batches=550):
    """
    Generates ~550 realistic grocery inventory batch records relative to current UTC time.
    Distributes batches across all 5 lifecycle states:
      - SAFE: > 7 days remaining (> 168 hours) -> ~420 batches (75%)
      - WARNING: > 2 days and <= 7 days (> 48h and <= 168h) -> ~40 batches
      - CRITICAL: > 6 hours and <= 2 days (> 6h and <= 48h) -> ~30 batches
      - DONATION: > 0 hours and <= 6 hours (> 0h and <= 6h) -> ~20 batches
      - EXPIRED: <= 0 hours (expired 1 to 14 days ago) -> ~30 batches
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    now = datetime.now(timezone.utc)

    # Gather flattened products list
    all_products = []
    for cat_data in CATEGORIES_WITH_PRODUCTS:
        category = cat_data["category"]
        mfr = cat_data["manufacturer"]
        for sku, p_name, base_price, mrp in cat_data["products"]:
            all_products.append({
                "sku": sku,
                "product_name": p_name,
                "category": category,
                "manufacturer": mfr,
                "base_price": base_price,
                "mrp": mrp,
            })

    # We will generate batches by picking products and assigning stage target buckets
    # Bucket definitions with time delta ranges relative to `now`
    stage_buckets = [
        # (stage_name, target_count, min_hours, max_hours)
        ("SAFE", 410, 170.0, 4320.0),       # 7.1 days to 180 days in future
        ("WARNING", 40, 50.0, 160.0),       # 2.1 days to 6.6 days in future
        ("CRITICAL", 35, 7.0, 45.0),        # 7 hours to 45 hours in future
        ("DONATION", 25, 0.5, 5.5),         # 30 mins to 5.5 hours in future
        ("EXPIRED", 30, -336.0, -1.0),      # 1 hour to 14 days in past
    ]

    records = []
    batch_counter = 1000

    for stage_name, target_count, min_h, max_h in stage_buckets:
        for _ in range(target_count):
            batch_counter += 1
            prod = random.choice(all_products)
            
            # Generate remaining hours for this stage
            rem_h = random.uniform(min_h, max_h)
            expiry_dt = now + timedelta(hours=rem_h)

            # Generate manufacturing date (1 to 12 months before expiry)
            mfg_days_before = random.randint(90, 365)
            mfg_dt = expiry_dt - timedelta(days=mfg_days_before)

            # Format strings
            mfg_str = mfg_dt.strftime("%Y-%m-%d")
            
            # Format expiry date string
            # For DONATION / CRITICAL / EXPIRED, include exact timestamp or YYYY-MM-DD
            if stage_name in ["DONATION", "CRITICAL"] or random.random() < 0.3:
                exp_str = expiry_dt.strftime("%Y-%m-%d %H:%M:%S")
            else:
                exp_str = expiry_dt.strftime("%Y-%m-%d")

            # Batch number format e.g. BATCH-MP001-1001
            code_prefix = prod["sku"].split("-")[1][:3].upper()
            batch_no = f"B{code_prefix}-{batch_counter}"

            # Stock quantity and daily demand
            stock_qty = random.randint(15, 350)
            daily_demand = random.randint(2, 28)

            records.append({
                "sku": prod["sku"],
                "product_name": prod["product_name"],
                "category": prod["category"],
                "manufacturer": prod["manufacturer"],
                "base_price": prod["base_price"],
                "mrp": prod["mrp"],
                "batch_number": batch_no,
                "manufacturing_date": mfg_str,
                "expiry_date": exp_str,
                "stock_quantity": stock_qty,
                "daily_demand": daily_demand,
                "status": stage_name,
            })

    # Shuffle records so stages are interspersed realistically
    random.shuffle(records)

    # Write CSV
    fieldnames = [
        "sku",
        "product_name",
        "category",
        "manufacturer",
        "base_price",
        "mrp",
        "batch_number",
        "manufacturing_date",
        "expiry_date",
        "stock_quantity",
        "daily_demand",
        "status",
    ]

    with open(output_path, mode="w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)

    print(f"Successfully generated {len(records)} mock inventory batch records in {output_path}.")
    return len(records)


if __name__ == "__main__":
    generate_mock_inventory_csv()
