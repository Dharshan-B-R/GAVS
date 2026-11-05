import 'package:flutter/material.dart';

void main() {
  runApp(const KiranaAIApp());
}

class KiranaAIApp extends StatelessWidget {
  const KiranaAIApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'KiranaAI',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        useMaterial3: true,
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF16845B),
        ),
        scaffoldBackgroundColor: const Color(0xFFF5F8F5),
      ),
      home: const KiranaHomePage(),
    );
  }
}

class Product {
  String name;
  String category;
  int quantity;
  double price;

  Product({
    required this.name,
    required this.category,
    required this.quantity,
    required this.price,
  });
}

class KiranaHomePage extends StatefulWidget {
  const KiranaHomePage({super.key});

  @override
  State<KiranaHomePage> createState() => _KiranaHomePageState();
}

class _KiranaHomePageState extends State<KiranaHomePage> {
  int selectedIndex = 0;

  final List<Product> products = [
    Product(
      name: 'Rice',
      category: 'Grains',
      quantity: 25,
      price: 60,
    ),
    Product(
      name: 'Cooking Oil',
      category: 'Essentials',
      quantity: 8,
      price: 140,
    ),
    Product(
      name: 'Sugar',
      category: 'Essentials',
      quantity: 15,
      price: 45,
    ),
    Product(
      name: 'Milk',
      category: 'Dairy',
      quantity: 3,
      price: 30,
    ),
  ];

  final TextEditingController searchController = TextEditingController();

  String searchQuery = '';

  @override
  void dispose() {
    searchController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final pages = [
      buildDashboard(),
      buildInventory(),
      buildPurchasing(),
      buildSettings(),
    ];

    return Scaffold(
      body: SafeArea(child: pages[selectedIndex]),
      bottomNavigationBar: NavigationBar(
        selectedIndex: selectedIndex,
        onDestinationSelected: (index) {
          setState(() => selectedIndex = index);
        },
        destinations: const [
          NavigationDestination(
            icon: Icon(Icons.home_outlined),
            selectedIcon: Icon(Icons.home),
            label: 'Home',
          ),
          NavigationDestination(
            icon: Icon(Icons.inventory_2_outlined),
            selectedIcon: Icon(Icons.inventory_2),
            label: 'Inventory',
          ),
          NavigationDestination(
            icon: Icon(Icons.shopping_cart_outlined),
            selectedIcon: Icon(Icons.shopping_cart),
            label: 'Purchasing',
          ),
          NavigationDestination(
            icon: Icon(Icons.settings_outlined),
            selectedIcon: Icon(Icons.settings),
            label: 'Settings',
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: showVoiceAssistant,
        backgroundColor: const Color(0xFF16845B),
        foregroundColor: Colors.white,
        icon: const Icon(Icons.mic),
        label: const Text('Talk to AI'),
      ),
    );
  }

  Widget buildDashboard() {
    final lowStock = products.where((p) => p.quantity <= 5).length;

    return ListView(
      padding: const EdgeInsets.all(20),
      children: [
        const Text(
          'KiranaAI',
          style: TextStyle(fontSize: 28, fontWeight: FontWeight.bold),
        ),
        const SizedBox(height: 5),
        const Text(
          'Your smart shop assistant',
          style: TextStyle(color: Colors.black54),
        ),
        const SizedBox(height: 24),
        Container(
          padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(
            color: const Color(0xFF16845B),
            borderRadius: BorderRadius.circular(20),
          ),
          child: const Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(Icons.storefront, color: Colors.white, size: 35),
              SizedBox(height: 12),
              Text(
                'Welcome, Shop Owner!',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 22,
                  fontWeight: FontWeight.bold,
                ),
              ),
              SizedBox(height: 6),
              Text(
                'Manage your shop smarter with KiranaAI.',
                style: TextStyle(color: Colors.white),
              ),
            ],
          ),
        ),
        const SizedBox(height: 20),
        Row(
          children: [
            Expanded(
              child: statCard(
                'Total Products',
                '${products.length}',
                Icons.inventory_2,
                Colors.blue,
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: statCard(
                'Low Stock',
                '$lowStock',
                Icons.warning_amber_rounded,
                Colors.orange,
              ),
            ),
          ],
        ),
        const SizedBox(height: 24),
        const Text(
          'Quick Actions',
          style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
        ),
        const SizedBox(height: 12),
        Row(
          children: [
            Expanded(
              child: actionCard(
                'Inventory',
                Icons.inventory,
                () => setState(() => selectedIndex = 1),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: actionCard(
                'Purchasing',
                Icons.shopping_cart,
                () => setState(() => selectedIndex = 2),
              ),
            ),
          ],
        ),
        const SizedBox(height: 24),
        const Text(
          'Recent Inventory',
          style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
        ),
        const SizedBox(height: 10),
        ...products.take(4).map(buildProductCard),
      ],
    );
  }

  Widget buildInventory() {
    final filteredProducts = products.where((product) {
      return product.name.toLowerCase().contains(searchQuery.toLowerCase()) ||
          product.category.toLowerCase().contains(searchQuery.toLowerCase());
    }).toList();

    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(20, 20, 20, 12),
          child: Row(
            children: [
              const Expanded(
                child: Text(
                  'Inventory',
                  style: TextStyle(fontSize: 28, fontWeight: FontWeight.bold),
                ),
              ),
              IconButton.filled(
                tooltip: 'Add product',
                onPressed: showAddProductDialog,
                icon: const Icon(Icons.add),
              ),
            ],
          ),
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 20),
          child: TextField(
            controller: searchController,
            onChanged: (value) {
              setState(() => searchQuery = value);
            },
            decoration: InputDecoration(
              hintText: 'Search products...',
              prefixIcon: const Icon(Icons.search),
              filled: true,
              fillColor: Colors.white,
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(14),
                borderSide: BorderSide.none,
              ),
            ),
          ),
        ),
        Padding(
          padding: const EdgeInsets.all(20),
          child: Row(
            children: [
              Expanded(
                child: statCard(
                  'Products',
                  '${products.length}',
                  Icons.inventory_2,
                  Colors.blue,
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: statCard(
                  'Low Stock',
                  '${products.where((p) => p.quantity <= 5).length}',
                  Icons.warning_amber,
                  Colors.orange,
                ),
              ),
            ],
          ),
        ),
        Expanded(
          child: filteredProducts.isEmpty
              ? const Center(child: Text('No products found.'))
              : ListView.builder(
                  padding: const EdgeInsets.fromLTRB(16, 0, 16, 90),
                  itemCount: filteredProducts.length,
                  itemBuilder: (context, index) {
                    return buildProductCard(filteredProducts[index]);
                  },
                ),
        ),
      ],
    );
  }

  Widget buildProductCard(Product product) {
    final isLowStock = product.quantity <= 5;

    return Card(
      color: Colors.white,
      elevation: 0,
      margin: const EdgeInsets.only(bottom: 12),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: BorderSide(color: Colors.grey.shade200),
      ),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Row(
          children: [
            Container(
              width: 48,
              height: 48,
              decoration: BoxDecoration(
                color: isLowStock
                    ? Colors.orange.withValues(alpha: 0.12)
                    : const Color(0xFF16845B).withValues(alpha: 0.10),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Icon(
                Icons.inventory_2_outlined,
                color: isLowStock ? Colors.orange : const Color(0xFF16845B),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    product.name,
                    style: const TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  Text(
                    product.category,
                    style: const TextStyle(color: Colors.black54),
                  ),
                  const SizedBox(height: 5),
                  Text(
                    '₹${product.price.toStringAsFixed(2)} per unit',
                    style: const TextStyle(fontWeight: FontWeight.w500),
                  ),
                  Text(
                    isLowStock
                        ? 'Low stock: ${product.quantity} units'
                        : 'In stock: ${product.quantity} units',
                    style: TextStyle(
                      color: isLowStock ? Colors.red : Colors.green,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ],
              ),
            ),
            Column(
              children: [
                IconButton(
                  tooltip: 'Increase stock',
                  onPressed: () {
                    setState(() => product.quantity++);
                  },
                  icon: const Icon(Icons.add_circle_outline),
                ),
                Text(
                  '${product.quantity}',
                  style: const TextStyle(fontWeight: FontWeight.bold),
                ),
                IconButton(
                  tooltip: 'Decrease stock',
                  onPressed: product.quantity > 0
                      ? () {
                          setState(() => product.quantity--);
                        }
                      : null,
                  icon: const Icon(Icons.remove_circle_outline),
                ),
              ],
            ),
            PopupMenuButton<String>(
              onSelected: (value) {
                if (value == 'delete') {
                  setState(() => products.remove(product));
                }
              },
              itemBuilder: (context) => const [
                PopupMenuItem(
                  value: 'delete',
                  child: Text('Delete product'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Future<void> showAddProductDialog() async {
    final nameController = TextEditingController();
    final categoryController = TextEditingController();
    final quantityController = TextEditingController();
    final priceController = TextEditingController();

    final result = await showDialog<Product>(
      context: context,
      builder: (dialogContext) {
        return AlertDialog(
          title: const Text('Add New Product'),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                TextField(
                  controller: nameController,
                  decoration: const InputDecoration(
                    labelText: 'Product name',
                  ),
                ),
                TextField(
                  controller: categoryController,
                  decoration: const InputDecoration(
                    labelText: 'Category',
                  ),
                ),
                TextField(
                  controller: quantityController,
                  keyboardType: TextInputType.number,
                  decoration: const InputDecoration(
                    labelText: 'Quantity',
                  ),
                ),
                TextField(
                  controller: priceController,
                  keyboardType:
                      const TextInputType.numberWithOptions(decimal: true),
                  decoration: const InputDecoration(
                    labelText: 'Price per unit (₹)',
                  ),
                ),
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () {
                final name = nameController.text.trim();
                final category = categoryController.text.trim();
                final quantity = int.tryParse(quantityController.text);
                final price = double.tryParse(priceController.text);

                if (name.isEmpty ||
                    category.isEmpty ||
                    quantity == null ||
                    quantity < 0 ||
                    price == null ||
                    price < 0) {
                  ScaffoldMessenger.of(dialogContext).showSnackBar(
                    const SnackBar(
                      content: Text('Enter valid product details.'),
                    ),
                  );
                  return;
                }

                Navigator.pop(
                  dialogContext,
                  Product(
                    name: name,
                    category: category,
                    quantity: quantity,
                    price: price,
                  ),
                );
              },
              child: const Text('Add Product'),
            ),
          ],
        );
      },
    );

    nameController.dispose();
    categoryController.dispose();
    quantityController.dispose();
    priceController.dispose();

    if (result != null && mounted) {
      setState(() => products.add(result));

      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('${result.name} added successfully.')),
      );
    }
  }

  Widget buildPurchasing() {
    final lowStockProducts = products.where((p) => p.quantity <= 5).toList();

    return ListView(
      padding: const EdgeInsets.all(20),
      children: [
        const Text(
          'Smart Purchasing',
          style: TextStyle(fontSize: 28, fontWeight: FontWeight.bold),
        ),
        const SizedBox(height: 8),
        const Text('Review low-stock products before planning purchases.'),
        const SizedBox(height: 20),
        if (lowStockProducts.isEmpty)
          const Card(
            child: Padding(
              padding: EdgeInsets.all(20),
              child: Text('No low-stock products right now.'),
            ),
          )
        else
          ...lowStockProducts.map(
            (product) => Card(
              child: ListTile(
                leading: const Icon(
                  Icons.warning_amber_rounded,
                  color: Colors.orange,
                ),
                title: Text(product.name),
                subtitle: Text('${product.quantity} units remaining'),
                trailing: Text('₹${product.price.toStringAsFixed(2)}'),
              ),
            ),
          ),
        const SizedBox(height: 20),
        const Text(
          'Purchase approval',
          style: TextStyle(fontWeight: FontWeight.bold, fontSize: 18),
        ),
        const SizedBox(height: 8),
        const Text(
          'This prototype only identifies products that may need restocking. '
          'It does not place orders or contact suppliers.',
        ),
      ],
    );
  }

  Widget buildSettings() {
    return ListView(
      padding: const EdgeInsets.all(20),
      children: [
        const Text(
          'Settings',
          style: TextStyle(fontSize: 28, fontWeight: FontWeight.bold),
        ),
        const SizedBox(height: 20),
        const Card(
          child: ListTile(
            leading: Icon(Icons.store),
            title: Text('Shop Profile'),
            subtitle: Text('KiranaAI Demo Shop'),
          ),
        ),
        const Card(
          child: ListTile(
            leading: Icon(Icons.language),
            title: Text('Language'),
            subtitle: Text('English'),
          ),
        ),
        const Card(
          child: ListTile(
            leading: Icon(Icons.security),
            title: Text('Security'),
            subtitle: Text('Account and permissions'),
          ),
        ),
        const Card(
          child: ListTile(
            leading: Icon(Icons.cloud_sync),
            title: Text('Data Storage'),
            subtitle: Text('Local demo data; backend not connected'),
          ),
        ),
      ],
    );
  }

  Widget statCard(
    String title,
    String value,
    IconData icon,
    Color color,
  ) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: Colors.grey.shade200),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, color: color, size: 26),
          const SizedBox(height: 12),
          Text(
            value,
            style: const TextStyle(
              fontSize: 25,
              fontWeight: FontWeight.bold,
            ),
          ),
          Text(
            title,
            style: const TextStyle(color: Colors.black54),
          ),
        ],
      ),
    );
  }

  Widget actionCard(
    String title,
    IconData icon,
    VoidCallback onTap,
  ) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(16),
      child: Container(
        padding: const EdgeInsets.all(18),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: Colors.grey.shade200),
        ),
        child: Column(
          children: [
            Icon(icon, color: const Color(0xFF16845B), size: 30),
            const SizedBox(height: 10),
            Text(
              title,
              style: const TextStyle(fontWeight: FontWeight.w600),
            ),
          ],
        ),
      ),
    );
  }

  void showVoiceAssistant() {
    showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (context) {
        return Padding(
          padding: const EdgeInsets.all(28),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(
                Icons.mic,
                color: Color(0xFF16845B),
                size: 55,
              ),
              const SizedBox(height: 16),
              const Text(
                'KiranaAI Voice Assistant',
                style: TextStyle(
                  fontSize: 22,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(height: 10),
              const Text(
                'Voice recognition is not connected yet. '
                'We will add multilingual voice support in a later step.',
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 20),
              FilledButton(
                onPressed: () => Navigator.pop(context),
                child: const Text('Close'),
              ),
            ],
          ),
        );
      },
    );
  }
}