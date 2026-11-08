import 'package:flutter/material.dart';

import 'services/api_service.dart';



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



/// Represents a product returned by the FastAPI backend.

class Product {

  final int id;

  final String name;

  final String category;

  final double quantity;

  final double minimumStock;

  final double purchasePrice;

  final double sellingPrice;

  final String unit;

  final bool isActive;



  const Product({

    required this.id,

    required this.name,

    required this.category,

    required this.quantity,

    required this.minimumStock,

    required this.purchasePrice,

    required this.sellingPrice,

    required this.unit,

    required this.isActive,

  });



  /// Converts a backend product JSON object into a Flutter Product.

  factory Product.fromJson(Map<String, dynamic> json) {

    return Product(

      id: (json['id'] as num).toInt(),

      name: (json['name'] ?? '').toString(),

      category: (json['category'] ?? 'Uncategorized').toString(),

      quantity: (json['quantity'] as num?)?.toDouble() ?? 0,

      minimumStock: (json['minimum_stock'] as num?)?.toDouble() ?? 0,

      purchasePrice: (json['purchase_price'] as num?)?.toDouble() ?? 0,

      sellingPrice: (json['selling_price'] as num?)?.toDouble() ?? 0,

      unit: (json['unit'] ?? 'pieces').toString(),

      isActive: json['is_active'] as bool? ?? true,

    );

  }

}



class KiranaHomePage extends StatefulWidget {

  const KiranaHomePage({super.key});



  @override

  State<KiranaHomePage> createState() => _KiranaHomePageState();

}



class _KiranaHomePageState extends State<KiranaHomePage> {

  int selectedIndex = 0;



  final List<Product> products = [];

  final TextEditingController searchController =

      TextEditingController();



  String searchQuery = '';

  bool isLoading = true;

  bool isSaving = false;



  String? loadError;



  Map<String, dynamic> inventorySummary = {};

  bool? backendConnected;



  /// Loads initial backend data when the application starts.

  @override

  void initState() {

    super.initState();

    loadBackendData();

  }



  /// Releases the search controller when this screen is removed.

  @override

  void dispose() {

    searchController.dispose();

    super.dispose();

  }



  /// Loads products and inventory statistics from FastAPI.

  Future<void> loadBackendData({

    bool showMessage = false,

  }) async {

    setState(() {

      isLoading = true;

      loadError = null;

    });



    try {

      final results = await Future.wait([

        ApiService.getProducts(),

        ApiService.getInventorySummary(),

      ]);



      final loadedProducts =

          (results[0] as List<dynamic>)

              .map(

                (item) => Product.fromJson(

                  item as Map<String, dynamic>,

                ),

              )

              .toList();



      final summary =

          results[1] as Map<String, dynamic>;



      if (!mounted) return;



      setState(() {

        products

          ..clear()

          ..addAll(loadedProducts);



        inventorySummary = summary;

        isLoading = false;

        backendConnected = true;

      });



      if (showMessage) {

        showSnackBar(

          'Inventory refreshed from the database.',

        );

      }

    } catch (error) {

      if (!mounted) return;



      setState(() {

        isLoading = false;

        backendConnected = false;

        loadError = error.toString();

      });



      if (showMessage) {

        showSnackBar(

          'Could not refresh inventory: $error',

          isError: true,

        );

      }

    }

  }



  /// Displays a short success or error message.

  void showSnackBar(

    String message, {

    bool isError = false,

  }) {

    ScaffoldMessenger.of(context).showSnackBar(

      SnackBar(

        content: Text(message),

        backgroundColor: isError

            ? Colors.red

            : const Color(0xFF16845B),

      ),

    );

  }



  /// Checks whether the FastAPI health endpoint can be reached.

  Future<void> testBackendConnection() async {

    final connected =

        await ApiService.checkConnection();



    if (!mounted) return;



    setState(() {

      backendConnected = connected;

    });



    showSnackBar(

      connected

          ? 'KiranaAI backend connected!'

          : 'Backend connection failed.',

      isError: !connected,

    );

  }



  /// Adds a product through POST /products.

  Future<void> createProduct(

    Map<String, dynamic> productData,

  ) async {

    setState(() {

      isSaving = true;

    });



    try {

      await ApiService.addProduct(productData);



      await loadBackendData();



      if (mounted) {

        showSnackBar('Product added successfully.');

      }

    } catch (error) {

      if (mounted) {

        showSnackBar(

          'Unable to add product: $error',

          isError: true,

        );

      }

    } finally {

      if (mounted) {

        setState(() {

          isSaving = false;

        });

      }

    }

  }



  /// Updates the product quantity through PUT /products/{productId}.

  Future<void> changeStock(

    Product product,

    double difference,

  ) async {

    final newQuantity =

        product.quantity + difference;



    if (newQuantity < 0) return;



    try {

      await ApiService.updateProduct(

        product.id,

        {'quantity': newQuantity},

      );



      await loadBackendData();



      if (mounted) {

        showSnackBar('Stock updated successfully.');

      }

    } catch (error) {

      if (mounted) {

        showSnackBar(

          'Stock update failed: $error',

          isError: true,

        );

      }

    }

  }



  /// Deletes a product through DELETE /products/{productId}.

  Future<void> deleteProduct(Product product) async {

    final confirmed = await showDialog<bool>(

      context: context,

      builder: (dialogContext) {

        return AlertDialog(

          title: const Text('Delete product?'),

          content: Text(

            'Delete "${product.name}" from the inventory?',

          ),

          actions: [

            TextButton(

              onPressed: () {

                Navigator.pop(dialogContext, false);

              },

              child: const Text('Cancel'),

            ),

            FilledButton(

              onPressed: () {

                Navigator.pop(dialogContext, true);

              },

              style: FilledButton.styleFrom(

                backgroundColor: Colors.red,

              ),

              child: const Text('Delete'),

            ),

          ],

        );

      },

    );



    if (confirmed != true) return;



    try {

      await ApiService.deleteProduct(product.id);



      await loadBackendData();



      if (mounted) {

        showSnackBar('Product deleted successfully.');

      }

    } catch (error) {

      if (mounted) {

        showSnackBar(

          'Delete failed: $error',

          isError: true,

        );

      }

    }

  }



    /// Builds the selected application page.

  @override

  Widget build(BuildContext context) {

    final pages = [

      buildDashboard(),

      buildInventory(),

      buildPurchasing(),

      buildSettings(),

    ];



    return Scaffold(

      body: SafeArea(

        child: pages[selectedIndex],

      ),

      bottomNavigationBar: NavigationBar(

        selectedIndex: selectedIndex,

        onDestinationSelected: (index) {

          setState(() {

            selectedIndex = index;

          });



          if (index == 1) {

            loadBackendData();

          }

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



  /// Builds the dashboard using live inventory summary values.

  Widget buildDashboard() {

    final totalProducts =

        inventorySummary['total_products'] ?? products.length;



    final lowStock =

        inventorySummary['low_stock_count'] ??

        products

            .where((p) => p.quantity <= p.minimumStock)

            .length;



    final totalQuantity =

        inventorySummary['total_stock_quantity'] ?? 0;



    final purchaseValue =

        inventorySummary['total_inventory_purchase_value'] ?? 0;



    return RefreshIndicator(

      onRefresh: () => loadBackendData(showMessage: true),

      child: ListView(

        padding: const EdgeInsets.all(20),

        children: [

          const Text(

            'KiranaAI',

            style: TextStyle(

              fontSize: 28,

              fontWeight: FontWeight.bold,

            ),

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

                Icon(

                  Icons.storefront,

                  color: Colors.white,

                  size: 35,

                ),

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



          if (isLoading)

            const LinearProgressIndicator()

          else if (loadError != null)

            _errorCard()

          else ...[

            Row(

              children: [

                Expanded(

                  child: statCard(

                    'Total Products',

                    '$totalProducts',

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



            const SizedBox(height: 12),



            Row(

              children: [

                Expanded(

                  child: statCard(

                    'Total Stock',

                    '$totalQuantity',

                    Icons.warehouse_outlined,

                    const Color(0xFF16845B),

                  ),

                ),

                const SizedBox(width: 12),

                Expanded(

                  child: statCard(

                    'Purchase Value',

                    '₹${purchaseValue is num ? purchaseValue.toStringAsFixed(2) : purchaseValue}',

                    Icons.currency_rupee,

                    Colors.deepPurple,

                  ),

                ),

              ],

            ),

          ],



          const SizedBox(height: 24),



          const Text(

            'Quick Actions',

            style: TextStyle(

              fontSize: 20,

              fontWeight: FontWeight.bold,

            ),

          ),



          const SizedBox(height: 12),



          Row(

            children: [

              Expanded(

                child: actionCard(

                  'Inventory',

                  Icons.inventory,

                  () {

                    setState(() {

                      selectedIndex = 1;

                    });

                    loadBackendData();

                  },

                ),

              ),

              const SizedBox(width: 12),

              Expanded(

                child: actionCard(

                  'Purchasing',

                  Icons.shopping_cart,

                  () {

                    setState(() {

                      selectedIndex = 2;

                    });

                  },

                ),

              ),

            ],

          ),



          const SizedBox(height: 24),



          const Text(

            'Recent Inventory',

            style: TextStyle(

              fontSize: 20,

              fontWeight: FontWeight.bold,

            ),

          ),



          const SizedBox(height: 10),



          if (!isLoading && loadError == null)

            ...products.take(4).map(buildProductCard),

        ],

      ),

    );

  }



  /// Shows a retry card when the backend cannot be reached.

  Widget _errorCard() {

    return Card(

      child: Padding(

        padding: const EdgeInsets.all(16),

        child: Column(

          children: [

            const Icon(

              Icons.cloud_off,

              color: Colors.red,

              size: 32,

            ),

            const SizedBox(height: 8),

            const Text('Unable to load backend data.'),

            const SizedBox(height: 6),

            Text(

              loadError ?? '',

              maxLines: 3,

              overflow: TextOverflow.ellipsis,

              textAlign: TextAlign.center,

            ),

            const SizedBox(height: 10),

            FilledButton.icon(

              onPressed: () {

                loadBackendData(showMessage: true);

              },

              icon: const Icon(Icons.refresh),

              label: const Text('Retry'),

            ),

          ],

        ),

      ),

    );

  }





    /// Builds the inventory page with live products, search and refresh.

  Widget buildInventory() {

    final filteredProducts = products.where((product) {

      final query = searchQuery.toLowerCase();



      return product.name.toLowerCase().contains(query) ||

          product.category.toLowerCase().contains(query);

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

                  style: TextStyle(

                    fontSize: 28,

                    fontWeight: FontWeight.bold,

                  ),

                ),

              ),

              IconButton(

                tooltip: 'Refresh inventory',

                onPressed: () {

                  loadBackendData(showMessage: true);

                },

                icon: const Icon(Icons.refresh),

              ),

              IconButton.filled(

                tooltip: 'Add product',

                onPressed: isSaving ? null : showAddProductDialog,

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

              setState(() {

                searchQuery = value;

              });

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

                  '${inventorySummary['total_products'] ?? products.length}',

                  Icons.inventory_2,

                  Colors.blue,

                ),

              ),

              const SizedBox(width: 10),

              Expanded(

                child: statCard(

                  'Low Stock',

                  '${inventorySummary['low_stock_count'] ?? products.where((p) => p.quantity <= p.minimumStock).length}',

                  Icons.warning_amber,

                  Colors.orange,

                ),

              ),

            ],

          ),

        ),



        if (isLoading)

          const LinearProgressIndicator(),



        if (loadError != null)

          _errorCard(),



        Expanded(

          child: loadError != null

              ? const SizedBox.shrink()

              : filteredProducts.isEmpty && !isLoading

                  ? const Center(

                      child: Text('No products found.'),

                    )

                  : ListView.builder(

                      padding: const EdgeInsets.fromLTRB(

                        16,

                        0,

                        16,

                        90,

                      ),

                      itemCount: filteredProducts.length,

                      itemBuilder: (context, index) {

                        return buildProductCard(

                          filteredProducts[index],

                        );

                      },

                    ),

        ),

      ],

    );

  }



  /// Builds one product card and sends stock changes to the backend.

  Widget buildProductCard(Product product) {

    final isLowStock =

        product.quantity <= product.minimumStock;



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

                    : const Color(0xFF16845B)

                        .withValues(alpha: 0.10),

                borderRadius: BorderRadius.circular(12),

              ),

              child: Icon(

                Icons.inventory_2_outlined,

                color: isLowStock

                    ? Colors.orange

                    : const Color(0xFF16845B),

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

                    style: const TextStyle(

                      color: Colors.black54,

                    ),

                  ),

                  const SizedBox(height: 5),

                  Text(

                    '₹${product.sellingPrice.toStringAsFixed(2)} per ${product.unit}',

                    style: const TextStyle(

                      fontWeight: FontWeight.w500,

                    ),

                  ),

                  Text(

                    isLowStock

                        ? 'Low stock: ${product.quantity} ${product.unit}'

                        : 'In stock: ${product.quantity} ${product.unit}',

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

                    changeStock(product, 1);

                  },

                  icon: const Icon(

                    Icons.add_circle_outline,

                  ),

                ),

                Text(

                  product.quantity.toStringAsFixed(

                    product.quantity % 1 == 0 ? 0 : 2,

                  ),

                  style: const TextStyle(

                    fontWeight: FontWeight.bold,

                  ),

                ),

                IconButton(

                  tooltip: 'Decrease stock',

                  onPressed: product.quantity >= 1

                      ? () {

                          changeStock(product, -1);

                        }

                      : null,

                  icon: const Icon(

                    Icons.remove_circle_outline,

                  ),

                ),

              ],

            ),



            PopupMenuButton<String>(

              onSelected: (value) {

                if (value == 'delete') {

                  deleteProduct(product);

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



  /// Opens the independent Add Product dialog and submits its validated data.
  /// Method: GET dialog result, then POST /products through createProduct().
  Future<void> showAddProductDialog() async {
    final result = await showDialog<Map<String, dynamic>>(
      context: context,
      barrierDismissible: false,
      builder: (dialogContext) => const AddProductDialog(),
    );

    if (result != null && mounted) {
      await createProduct(result);
    }
  }

  /// Shows products that need replenishment based on backend stock levels.

  Widget buildPurchasing() {

    final lowStockProducts = products

        .where((p) => p.quantity <= p.minimumStock)

        .toList();



    return RefreshIndicator(

      onRefresh: () => loadBackendData(showMessage: true),

      child: ListView(

        padding: const EdgeInsets.all(20),

        children: [

          const Text(

            'Smart Purchasing',

            style: TextStyle(

              fontSize: 28,

              fontWeight: FontWeight.bold,

            ),

          ),

          const SizedBox(height: 8),

          const Text(

            'Review low-stock products before planning purchases.',

          ),

          const SizedBox(height: 20),



          if (isLoading)

            const LinearProgressIndicator(),



          if (loadError != null)

            _errorCard(),



          if (!isLoading &&

              loadError == null &&

              lowStockProducts.isEmpty)

            const Card(

              child: Padding(

                padding: EdgeInsets.all(20),

                child: Text(

                  'No low-stock products right now.',

                ),

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

                  subtitle: Text(

                    '${product.quantity} ${product.unit} remaining · '

                    'Minimum ${product.minimumStock}',

                  ),

                  trailing: Text(

                    '₹${product.purchasePrice.toStringAsFixed(2)}',

                  ),

                ),

              ),

            ),



          const SizedBox(height: 20),



          const Text(

            'Purchase approval',

            style: TextStyle(

              fontWeight: FontWeight.bold,

              fontSize: 18,

            ),

          ),



          const SizedBox(height: 8),



          const Text(

            'Review recommendations before purchasing. KiranaAI does not '

            'place orders or contact suppliers without owner approval.',

          ),

        ],

      ),

    );

  }



  /// Displays application settings and the live backend connection status.

  Widget buildSettings() {

    return ListView(

      padding: const EdgeInsets.all(20),

      children: [

        const Text(

          'Settings',

          style: TextStyle(

            fontSize: 28,

            fontWeight: FontWeight.bold,

          ),

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



        Card(

          child: ListTile(

            leading: Icon(

              backendConnected == true

                  ? Icons.cloud_done

                  : Icons.cloud_sync,

              color: backendConnected == true

                  ? Colors.green

                  : Colors.orange,

            ),

            title: const Text('Backend Connection'),

            subtitle: Text(

              backendConnected == true

                  ? 'Connected to FastAPI and PostgreSQL'

                  : backendConnected == false

                      ? 'Connection unavailable'

                      : 'Checking connection...',

            ),

            trailing: const Icon(

              Icons.arrow_forward_ios,

              size: 16,

            ),

            onTap: testBackendConnection,

          ),

        ),



        Card(

          child: ListTile(

            leading: const Icon(Icons.storage),

            title: const Text('Data Storage'),

            subtitle: const Text(

              'Live data from the KiranaAI backend',

            ),

            trailing: IconButton(

              tooltip: 'Refresh data',

              onPressed: () {

                loadBackendData(showMessage: true);

              },

              icon: const Icon(Icons.refresh),

            ),

          ),

        ),

      ],

    );

  }



  /// Builds a reusable dashboard statistic card.

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

        border: Border.all(

          color: Colors.grey.shade200,

        ),

      ),

      child: Column(

        crossAxisAlignment: CrossAxisAlignment.start,

        children: [

          Icon(

            icon,

            color: color,

            size: 26,

          ),

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

            style: const TextStyle(

              color: Colors.black54,

            ),

          ),

        ],

      ),

    );

  }



  /// Builds a reusable dashboard shortcut card.

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

          border: Border.all(

            color: Colors.grey.shade200,

          ),

        ),

        child: Column(

          children: [

            Icon(

              icon,

              color: const Color(0xFF16845B),

              size: 30,

            ),

            const SizedBox(height: 10),

            Text(

              title,

              style: const TextStyle(

                fontWeight: FontWeight.w600,

              ),

            ),

          ],

        ),

      ),

    );

  }



  /// Displays the current voice assistant placeholder.

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

                onPressed: () {

                  Navigator.pop(context);

                },

                child: const Text('Close'),

              ),

            ],

          ),

        );

      },

    );

  }

}

/// ------------------------------------------------------------
/// WIDGET: AddProductDialog
/// Purpose: Own the Add Product form and its text controllers.
/// Controllers are disposed with this widget, after its text fields
/// are removed from the widget tree.
/// ------------------------------------------------------------
class AddProductDialog extends StatefulWidget {
  const AddProductDialog({super.key});

  @override
  State<AddProductDialog> createState() => _AddProductDialogState();
}

class _AddProductDialogState extends State<AddProductDialog> {
  final _formKey = GlobalKey<FormState>();
  final _nameController = TextEditingController();
  final _categoryController = TextEditingController();
  final _quantityController = TextEditingController(text: '0');
  final _minimumController = TextEditingController(text: '0');
  final _purchaseController = TextEditingController(text: '0');
  final _sellingController = TextEditingController(text: '0');
  final _unitController = TextEditingController(text: 'pieces');

  /// Releases all form controllers when the dialog widget is removed.
  @override
  void dispose() {
    _nameController.dispose();
    _categoryController.dispose();
    _quantityController.dispose();
    _minimumController.dispose();
    _purchaseController.dispose();
    _sellingController.dispose();
    _unitController.dispose();
    super.dispose();
  }

  /// Validates the form and returns the product data to the parent screen.
  void _submitProduct() {
    if (!_formKey.currentState!.validate()) {
      return;
    }

    Navigator.of(context).pop({
      'name': _nameController.text.trim(),
      'category': _categoryController.text.trim().isEmpty
          ? null
          : _categoryController.text.trim(),
      'quantity': double.parse(_quantityController.text.trim()),
      'minimum_stock': double.parse(_minimumController.text.trim()),
      'purchase_price': double.parse(_purchaseController.text.trim()),
      'selling_price': double.parse(_sellingController.text.trim()),
      'unit': _unitController.text.trim().isEmpty
          ? 'pieces'
          : _unitController.text.trim(),
    });
  }

  /// Builds one validated text field for the Add Product form.
  Widget _buildFormField(
    TextEditingController controller,
    String label, {
    bool number = false,
    bool isRequired = false,
  }) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: TextFormField(
        controller: controller,
        keyboardType: number
            ? const TextInputType.numberWithOptions(decimal: true)
            : TextInputType.text,
        decoration: InputDecoration(labelText: label),
        validator: (value) {
          final text = value?.trim() ?? '';

          if (isRequired && text.isEmpty) {
            return 'Enter $label';
          }

          if (number) {
            if (text.isEmpty) {
              return 'Enter $label';
            }

            final parsed = double.tryParse(text);
            if (parsed == null || !parsed.isFinite || parsed < 0) {
              return 'Enter a valid number';
            }
          }

          return null;
        },
      ),
    );
  }

  /// Displays the Add Product form and its Cancel and Save actions.
  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Add New Product'),
      content: SizedBox(
        width: 420,
        child: Form(
          key: _formKey,
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                _buildFormField(
                  _nameController,
                  'Product name',
                  isRequired: true,
                ),
                _buildFormField(_categoryController, 'Category'),
                _buildFormField(
                  _quantityController,
                  'Quantity',
                  number: true,
                ),
                _buildFormField(
                  _minimumController,
                  'Minimum stock',
                  number: true,
                ),
                _buildFormField(
                  _purchaseController,
                  'Purchase price',
                  number: true,
                ),
                _buildFormField(
                  _sellingController,
                  'Selling price',
                  number: true,
                ),
                _buildFormField(_unitController, 'Unit'),
              ],
            ),
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: _submitProduct,
          child: const Text('Save Product'),
        ),
      ],
    );
  }
}

