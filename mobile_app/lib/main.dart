import 'dart:convert';

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

      home: const AuthGate(),

    );

  }

}



class AuthGate extends StatefulWidget {
  const AuthGate({super.key});

  @override
  State<AuthGate> createState() => _AuthGateState();
}

class _AuthGateState extends State<AuthGate> {
  bool _checking = true;
  Map<String, dynamic>? _user;
  Map<String, dynamic>? _activeShop;
  String? _error;

  @override
  void initState() { super.initState(); _restoreSession(); }

  Future<void> _loadIdentity() async {
    final user = await ApiService.getCurrentUser();
    final role = (user['role'] ?? '').toString().toLowerCase();
    Map<String, dynamic>? shop;
    if (role == 'owner' || role == 'employee') {
      final shops = await ApiService.refreshMyShops();
      if (shops.isEmpty) throw Exception('Your account has no active shop membership.');
      shop = await ApiService.getActiveShop();
      if (shop == null) throw Exception('No active shop is selected for this account.');
    } else if (role != 'supplier' && role != 'admin') {
      throw Exception('This account role is not supported by the app.');
    }
    if (mounted) setState(() { _user = user; _activeShop = shop; });
  }

  Future<void> _restoreSession() async {
    try {
      if (await ApiService.hasAccessToken()) await _loadIdentity();
    } catch (error) {
      await ApiService.logout();
      _error = error.toString().replaceFirst('Exception: ', '');
    } finally {
      if (mounted) setState(() => _checking = false);
    }
  }

  Future<void> _onLogin() async {
    try {
      await _loadIdentity();
      if (mounted) {
        setState(() => _error = null);
      }
    } catch (error) {
      await ApiService.logout();
      if (mounted) {
        setState(() {
          _user = null;
          _activeShop = null;
          _error = error.toString().replaceFirst('Exception: ', '');
        });
      }
    }
  }

  Future<void> _onLogout() async {
    await ApiService.logout();
    if (mounted) {
      setState(() {
        _user = null;
        _activeShop = null;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_checking) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    if (_user == null) {
      return LoginScreen(onLogin: _onLogin, initialError: _error);
    }

    final role = (_user!['role'] ?? '').toString().toLowerCase();
    final identity = (_user!['full_name'] ?? _user!['email']).toString();
    if (role == 'supplier') {
      return RoleLandingScreen(title: 'Distributor workspace',
        subtitle: 'Signed in as $identity',
        description: 'Your distributor account is authenticated. Supplier catalogue, shop connections and order fulfilment will appear here.',
        onLogout: _onLogout);
    }
    if (role == 'admin') {
      return RoleLandingScreen(title: 'Administration',
        subtitle: 'Signed in as $identity',
        description: 'Administrator access is separate from shop-owner access. Admin tools will be enabled here.',
        onLogout: _onLogout);
    }
    return KiranaHomePage(userRole: role,
      shopName: (_activeShop?['name'] ?? 'My shop').toString(),
      onLogout: _onLogout);
  }
}

class RoleLandingScreen extends StatelessWidget {
  const RoleLandingScreen({super.key, required this.title, required this.subtitle,
    required this.description, required this.onLogout});
  final String title;
  final String subtitle;
  final String description;
  final Future<void> Function() onLogout;

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: Text(title), actions: [
      IconButton(tooltip: 'Sign out', onPressed: onLogout, icon: const Icon(Icons.logout)),
    ]),
    body: Center(child: ConstrainedBox(
      constraints: const BoxConstraints(maxWidth: 520),
      child: Card(margin: const EdgeInsets.all(24), child: Padding(
        padding: const EdgeInsets.all(28),
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          const Icon(Icons.verified_user_outlined, size: 52, color: Color(0xFF16845B)),
          const SizedBox(height: 16),
          Text(title, style: Theme.of(context).textTheme.headlineSmall),
          const SizedBox(height: 8),
          Text(subtitle, textAlign: TextAlign.center),
          const SizedBox(height: 18),
          Text(description, textAlign: TextAlign.center),
          const SizedBox(height: 20),
          const Text('Role-based session active',
            style: TextStyle(color: Color(0xFF16845B), fontWeight: FontWeight.w600)),
        ]),
      )),
    )),
  );
}

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key, required this.onLogin, this.initialError});
  final VoidCallback onLogin;
  final String? initialError;

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _formKey = GlobalKey<FormState>();
  final _email = TextEditingController();
  final _password = TextEditingController();
  bool _busy = false;
  bool _obscure = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _error = widget.initialError;
  }

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() { _busy = true; _error = null; });
    try {
      await ApiService.login(email: _email.text.trim(), password: _password.text);
      if (mounted) widget.onLogin();
    } catch (error) {
      if (mounted) {
        setState(() => _error = error.toString().replaceFirst('Exception: ', ''));
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 420),
            child: Card(
              child: Padding(
                padding: const EdgeInsets.all(28),
                child: Form(
                  key: _formKey,
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      const Icon(Icons.storefront, size: 56, color: Color(0xFF16845B)),
                      const SizedBox(height: 12),
                      const Text('KiranaAI', textAlign: TextAlign.center,
                        style: TextStyle(fontSize: 28, fontWeight: FontWeight.bold)),
                      const SizedBox(height: 6),
                      const Text('Sign in to manage your shop', textAlign: TextAlign.center,
                        style: TextStyle(color: Colors.black54)),
                      const SizedBox(height: 24),
                      TextFormField(
                        controller: _email,
                        keyboardType: TextInputType.emailAddress,
                        autofillHints: const [AutofillHints.username, AutofillHints.email],
                        decoration: const InputDecoration(
                          labelText: 'Email',
                          prefixIcon: Icon(Icons.email_outlined),
                          border: OutlineInputBorder(),
                        ),
                        validator: (value) => value == null || !value.contains('@')
                            ? 'Enter a valid email' : null,
                      ),
                      const SizedBox(height: 14),
                      TextFormField(
                        controller: _password,
                        obscureText: _obscure,
                        autofillHints: const [AutofillHints.password],
                        decoration: InputDecoration(
                          labelText: 'Password',
                          prefixIcon: const Icon(Icons.lock_outline),
                          border: const OutlineInputBorder(),
                          suffixIcon: IconButton(
                            onPressed: () => setState(() => _obscure = !_obscure),
                            icon: Icon(_obscure ? Icons.visibility : Icons.visibility_off),
                          ),
                        ),
                        validator: (value) => value == null || value.isEmpty
                            ? 'Enter your password' : null,
                        onFieldSubmitted: (_) { if (!_busy) _submit(); },
                      ),
                      if (_error != null) ...[
                        const SizedBox(height: 12),
                        Text(_error!, style: const TextStyle(color: Colors.red)),
                      ],
                      const SizedBox(height: 20),
                      FilledButton(
                        onPressed: _busy ? null : _submit,
                        child: Padding(
                          padding: const EdgeInsets.symmetric(vertical: 12),
                          child: _busy
                              ? const SizedBox(height: 20, width: 20,
                                  child: CircularProgressIndicator(strokeWidth: 2))
                              : const Text('Sign in'),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
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

  const KiranaHomePage({super.key, required this.onLogout, required this.userRole, required this.shopName});

  final Future<void> Function() onLogout;
  final String userRole;
  final String shopName;



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



  
  // Backend-generated restock recommendation state.
  List<Map<String, dynamic>> restockRecommendations = [];
  final Set<int> selectedRestockProducts = <int>{};
  bool isRestockLoading = false;
  String? restockError;
  bool purchasePlanApproved = false;
  List<dynamic> _shopSuppliers = [];
  List<dynamic> _purchaseProposals = [];
  List<dynamic> _purchaseOrders = [];
  int? _selectedSupplierId;
  final TextEditingController _budgetController = TextEditingController();
  final TextEditingController _supplierIdController = TextEditingController();
  bool _purchasePlanningLoading = false;
  bool _budgetSaving = false;
  final TextEditingController _saleQuantityController = TextEditingController(text: '1');
  final TextEditingController _aiQuestionController = TextEditingController();
  int? _saleProductId;
  String _salePaymentMethod = 'cash';
  final Map<int, double> _saleCart = {};
  List<dynamic> _salesHistory = [];
  bool _salesLoading = false;
  bool _saleSubmitting = false;
  bool _aiLoading = false;
  final List<Map<String, String>> _aiMessages = [
    {'role': 'assistant', 'text': 'Ask about low stock, expiry, dead stock, sales trends, forecasts or reorder recommendations.'},
  ];
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



      
      loadRestockRecommendations();
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

  Future<void> changeStock(Product product, double difference) async {
    try {
      if (difference > 0) {
        final batchController = TextEditingController();
        DateTime? expiryDate;
        final details = await showDialog<Map<String, dynamic>>(
          context: context,
          builder: (dialogContext) => StatefulBuilder(
            builder: (context, setDialogState) => AlertDialog(
              title: Text('Add stock · ${product.name}'),
              content: Column(mainAxisSize: MainAxisSize.min, children: [
                TextField(controller: batchController,
                  decoration: const InputDecoration(labelText: 'Batch number')),
                const SizedBox(height: 12),
                OutlinedButton.icon(
                  onPressed: () async {
                    final selected = await showDatePicker(
                      context: context,
                      firstDate: DateTime.now(),
                      lastDate: DateTime(2100),
                      initialDate: DateTime.now().add(const Duration(days: 180)),
                    );
                    if (selected != null) setDialogState(() => expiryDate = selected);
                  },
                  icon: const Icon(Icons.calendar_today),
                  label: Text(expiryDate == null ? 'Select expiry date' :
                    'Expiry: ${expiryDate!.toIso8601String().substring(0, 10)}'),
                ),
                const SizedBox(height: 8),
                const Text('New stock remains unavailable for sale until its batch is verified.',
                  style: TextStyle(color: Colors.black54)),
              ]),
              actions: [
                TextButton(onPressed: () => Navigator.pop(dialogContext), child: const Text('Cancel')),
                FilledButton(
                  onPressed: () {
                    if (batchController.text.trim().isEmpty || expiryDate == null) return;
                    Navigator.pop(dialogContext, {
                      'batch': batchController.text.trim(),
                      'expiry': expiryDate!.toIso8601String().substring(0, 10),
                    });
                  },
                  child: const Text('Add batch'),
                ),
              ],
            ),
          ),
        );
        batchController.dispose();
        if (details == null) return;
        await ApiService.adjustStock(
          productId: product.id,
          quantityChange: difference,
          reason: 'Manual stock addition',
          batchNumber: details['batch'] as String,
          expiryDate: details['expiry'] as String,
        );
      } else {
        await ApiService.adjustStock(
          productId: product.id,
          quantityChange: difference,
          reason: 'Manual stock reduction / wastage',
        );
      }
      await loadBackendData();
      if (mounted) showSnackBar('Audited stock adjustment recorded.');
    } catch (error) {
      if (mounted) showSnackBar('Stock adjustment failed: $error', isError: true);
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
      buildSales(),
      buildPurchasing(),
      buildAiAssistant(),
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
          } else if (index == 2) {
            _loadSalesHistory();
          } else if (index == 3) {
            loadBackendData();
            loadRestockRecommendations();
          }

        },

        destinations: const [
          NavigationDestination(icon: Icon(Icons.home_outlined), selectedIcon: Icon(Icons.home), label: 'Home'),
          NavigationDestination(icon: Icon(Icons.inventory_2_outlined), selectedIcon: Icon(Icons.inventory_2), label: 'Inventory'),
          NavigationDestination(icon: Icon(Icons.point_of_sale_outlined), selectedIcon: Icon(Icons.point_of_sale), label: 'Sales'),
          NavigationDestination(icon: Icon(Icons.shopping_cart_outlined), selectedIcon: Icon(Icons.shopping_cart), label: 'Purchasing'),
          NavigationDestination(icon: Icon(Icons.auto_awesome_outlined), selectedIcon: Icon(Icons.auto_awesome), label: 'AI Assistant'),
          NavigationDestination(icon: Icon(Icons.settings_outlined), selectedIcon: Icon(Icons.settings), label: 'Settings'),
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

                  
                    loadBackendData();
                    loadRestockRecommendations();
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


  Future<void> _loadPurchasePlanningData() async {
    if (widget.userRole != 'owner') return;
    setState(() => _purchasePlanningLoading = true);
    try {
      final results = await Future.wait([
        ApiService.getShopSuppliers(),
        ApiService.getPurchaseProposals(),
        ApiService.getShopPurchaseOrders(),
        ApiService.getPurchaseBudget(),
      ]);
      if (!mounted) return;
      final suppliers = results[0] as List<dynamic>;
      final budget = results[3] as Map<String, dynamic>;
      setState(() {
        _shopSuppliers = suppliers;
        _purchaseProposals = results[1] as List<dynamic>;
        _purchaseOrders = results[2] as List<dynamic>;
        _selectedSupplierId ??= suppliers.isNotEmpty
            ? (suppliers.first['supplier_id'] as num).toInt() : null;
        _budgetController.text = budget['available_amount']?.toString() ?? '0.00';
        _purchasePlanningLoading = false;
      });
    } catch (error) {
      if (mounted) {
        setState(() => _purchasePlanningLoading = false);
        showSnackBar('Purchase planning data could not be loaded: $error', isError: true);
      }
    }
  }

  Future<void> _savePurchaseBudget() async {
    final amount = double.tryParse(_budgetController.text.trim());
    if (amount == null || amount < 0) {
      showSnackBar('Enter a valid non-negative INR budget.', isError: true);
      return;
    }
    setState(() => _budgetSaving = true);
    try {
      await ApiService.setPurchaseBudget(amount);
      await _loadPurchasePlanningData();
      if (mounted) showSnackBar('Purchase budget saved.');
    } catch (error) {
      if (mounted) showSnackBar('Budget update failed: $error', isError: true);
    } finally {
      if (mounted) setState(() => _budgetSaving = false);
    }
  }

  Future<void> _connectSupplierById() async {
    final id = int.tryParse(_supplierIdController.text.trim());
    if (id == null || id <= 0) {
      showSnackBar('Enter a valid supplier ID.', isError: true);
      return;
    }
    try {
      await ApiService.connectSupplier(id);
      _supplierIdController.clear();
      await _loadPurchasePlanningData();
      if (mounted) showSnackBar('Supplier connected to this shop.');
    } catch (error) {
      if (mounted) showSnackBar('Could not connect supplier: $error', isError: true);
    }
  }

  Future<void> _createPurchaseProposal() async {
    if (widget.userRole != 'owner' || selectedRestockProducts.isEmpty) return;
    if (_selectedSupplierId == null) {
      showSnackBar('Connect and select a supplier before creating a proposal.', isError: true);
      return;
    }
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Create purchase proposal?'),
        content: Text('Create a proposal for ${selectedRestockProducts.length} selected product(s), estimated at ₹${_selectedPurchaseTotal().toStringAsFixed(2)}. This does not place an order.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(dialogContext, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(dialogContext, true), child: const Text('Create proposal')),
        ],
      ),
    );
    if (confirmed != true) return;
    try {
      final items = <Map<String, dynamic>>[];
      for (final recommendation in restockRecommendations) {
        final id = (recommendation['product_id'] as num?)?.toInt();
        if (id == null || !selectedRestockProducts.contains(id)) continue;
        final product = _productForRecommendation(recommendation);
        if (product == null) continue;
        final quantity = _recommendationNumber(
          recommendation['suggested_quantity'] ?? recommendation['suggested_reorder_quantity'],
        );
        if (quantity > 0) items.add({
          'product_id': id,
          'quantity': quantity,
          'unit_price': product.purchasePrice,
        });
      }
      if (items.isEmpty) throw Exception('No valid recommendation items selected.');
      await ApiService.createPurchaseProposal(
        supplierId: _selectedSupplierId,
        items: items,
        rationale: 'Created from KiranaAI reorder recommendations.',
      );
      if (!mounted) return;
      setState(() => selectedRestockProducts.clear());
      await _loadPurchasePlanningData();
      showSnackBar('Proposal created. Owner approval is still required.');
    } catch (error) {
      if (mounted) showSnackBar('Proposal creation failed: $error', isError: true);
    }
  }

  Future<void> _decideProposal(int proposalId, bool approve) async {
    try {
      await ApiService.decidePurchaseProposal(proposalId, approve: approve);
      await _loadPurchasePlanningData();
      if (mounted) showSnackBar(approve ? 'Proposal approved. No order has been placed yet.' : 'Proposal rejected.');
    } catch (error) {
      if (mounted) showSnackBar('Decision failed: $error', isError: true);
    }
  }

  Future<void> _executeProposal(int proposalId) async {
    try {
      final result = await ApiService.executePurchaseProposal(proposalId);
      await _loadPurchasePlanningData();
      if (mounted) showSnackBar('Internal PO ${result['purchase_order_number'] ?? result['purchase_id']} created. It has not been sent externally.');
    } catch (error) {
      if (mounted) showSnackBar('PO creation failed: $error', isError: true);
    }
  }

  Future<void> _receivePurchaseOrder(Map<String, dynamic> order) async {
    final items = (order['items'] as List<dynamic>? ?? []).cast<Map<String, dynamic>>();
    final receipt = await showDialog<List<Map<String, dynamic>>>(
      context: context,
      builder: (dialogContext) => ReceivePurchaseDialog(items: items, products: products),
    );
    if (receipt == null) return;
    try {
      await ApiService.receivePurchaseOrder((order['purchase_id'] as num).toInt(), receipt);
      await _loadPurchasePlanningData();
      await loadBackendData();
      if (mounted) showSnackBar('Goods receipt saved. Batches require verification before sale.');
    } catch (error) {
      if (mounted) showSnackBar('Goods receipt failed: $error', isError: true);
    }
  }

  /// Loads backend-generated replenishment recommendations.
  /// Method: GET /inventory/restock-recommendations?days=30&warning_days=7.
  Future<void> loadRestockRecommendations() async {
    if (!mounted) return;
    setState(() {
      isRestockLoading = true;
      restockError = null;
    });
    try {
      final response = await ApiService.getRestockRecommendations(
        days: 30,
        warningDays: 7,
      );
      final rawItems = response['recommendations'] as List<dynamic>? ?? [];
      final loadedItems = rawItems
          .whereType<Map<String, dynamic>>()
          .toList();
      if (!mounted) return;
      setState(() {
        restockRecommendations = loadedItems;
        selectedRestockProducts.removeWhere(
          (id) => !loadedItems.any(
            (item) => (item['product_id'] as num?)?.toInt() == id,
          ),
        );
        isRestockLoading = false;
      });
      await _loadPurchasePlanningData();
    } catch (error) {
      if (!mounted) return;
      setState(() {
        isRestockLoading = false;
        restockError = error.toString();
      });
    }
  }

  /// Finds the product record used to obtain its purchase price.
  Product? _productForRecommendation(Map<String, dynamic> recommendation) {
    final id = (recommendation['product_id'] as num?)?.toInt();
    for (final product in products) {
      if (product.id == id) return product;
    }
    return null;
  }

  /// Converts a backend numeric value safely to a double.
  double _recommendationNumber(dynamic value) {
    if (value is num) return value.toDouble();
    return double.tryParse(value?.toString() ?? '') ?? 0;
  }

  /// Calculates the estimated cost for one recommended product.
  double _recommendationCost(Map<String, dynamic> recommendation) {
    final product = _productForRecommendation(recommendation);
    final estimate = recommendation['estimated_total_cost'];
    if (estimate is num) return estimate.toDouble();
    final quantity = _recommendationNumber(
      recommendation['suggested_quantity'] ?? recommendation['suggested_reorder_quantity'],
    );
    return (product?.purchasePrice ?? 0) * quantity;
  }

  /// Calculates the estimated cost of all selected products.
  double _selectedPurchaseTotal() {
    return restockRecommendations
        .where((item) => selectedRestockProducts.contains(
              (item['product_id'] as num?)?.toInt(),
            ))
        .fold(0.0, (total, item) => total + _recommendationCost(item));
  }

  /// Requests owner confirmation for the selected purchase plan.
  /// This is a local confirmation only; it does not place an order.
  Future<void> _approvePurchasePlan() async {
    if (selectedRestockProducts.isEmpty) return;
    final total = _selectedPurchaseTotal();
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Confirm purchase plan'),
        content: Text(
             'You selected ${selectedRestockProducts.length} product(s). '
            'Estimated total: ₹${total.toStringAsFixed(2)}.\n\n'
            'This confirms your plan only. No order will be placed.',
              ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: const Text('Review again'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(dialogContext, true),
            child: const Text('Confirm plan'),
          ),
        ],
      ),
    );
    if (confirmed == true && mounted) {
      setState(() => purchasePlanApproved = true);
      showSnackBar('Purchase plan approved for review. No order was placed.');
    }
  }

  /// Formats quantities without unnecessary decimal zeroes.
  String _formatRecommendationQuantity(double value) {
    return value % 1 == 0
        ? value.toStringAsFixed(0)
        : value.toStringAsFixed(2);
  }

  /// Builds the Purchasing page from backend restock recommendations.
  /// Method: GET /inventory/restock-recommendations.
  Widget buildPurchasing() {
    final selectedCount = selectedRestockProducts.length;
    final selectedTotal = _selectedPurchaseTotal();

    return RefreshIndicator(
      onRefresh: () async {
        await loadBackendData();
        await loadRestockRecommendations();
      },
      child: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          const Text(
            'Smart Purchasing',
            style: TextStyle(fontSize: 28, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 8),
          const Text('Review stock recommendations before planning purchases.'),
          const SizedBox(height: 20),
          if (isLoading || isRestockLoading)
            const LinearProgressIndicator(),
          if (loadError != null) _errorCard(),
          if (restockError != null)
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'Could not load restock recommendations.',
                      style: TextStyle(fontWeight: FontWeight.w600),
                    ),
                    const SizedBox(height: 8),
                    Text(restockError!),
                    Align(
                      alignment: Alignment.centerRight,
                      child: TextButton.icon(
                        onPressed: loadRestockRecommendations,
                        icon: const Icon(Icons.refresh),
                        label: const Text('Retry'),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          if (!isRestockLoading &&
              restockError == null &&
              restockRecommendations.isEmpty)
            const Card(
              child: Padding(
                padding: EdgeInsets.all(20),
                child: Row(
                  children: [
                    Icon(Icons.check_circle_outline, color: Colors.green),
                    SizedBox(width: 12),
                    Expanded(
                      child: Text('No products currently require restocking.'),
                    ),
                  ],
                ),
              ),
            ),
          ...restockRecommendations.map((recommendation) {
            final product = _productForRecommendation(recommendation);
            final productId =
                (recommendation['product_id'] as num?)?.toInt() ?? -1;
            final name = recommendation['product_name']?.toString() ??
                product?.name ?? 'Unknown product';
            final unit = recommendation['unit']?.toString() ??
                product?.unit ?? 'pieces';
            final currentStock =
                _recommendationNumber(recommendation['saleable_stock'] ?? recommendation['current_stock']);
            final minimumStock = product?.minimumStock ??
                _recommendationNumber(recommendation['minimum_stock']);
            final averageDailySales =
                _recommendationNumber(recommendation['average_daily_demand'] ?? recommendation['average_daily_sales']);
            final suggestedQuantity = _recommendationNumber(
              recommendation['suggested_quantity'] ?? recommendation['suggested_reorder_quantity'],
            );
            final dailyDemand = _recommendationNumber(recommendation['average_daily_demand'] ?? recommendation['average_daily_sales']);
            final remainingDays = recommendation['estimated_days_remaining'] ??
                (dailyDemand > 0 ? currentStock / dailyDemand : null);
            final cost = _recommendationCost(recommendation);
            final selected = selectedRestockProducts.contains(productId);

            return Card(
              margin: const EdgeInsets.only(bottom: 12),
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        const Icon(
                          Icons.warning_amber_rounded,
                          color: Colors.orange,
                        ),
                        const SizedBox(width: 10),
                        Expanded(
                          child: Text(
                            name,
                            style: const TextStyle(
                              fontSize: 16,
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                        ),
                        Checkbox(
                          value: selected,
                          onChanged: productId < 0
                              ? null
                              : (value) {
                                  setState(() {
                                    if (value == true) {
                                      selectedRestockProducts.add(productId);
                                    } else {
                                      selectedRestockProducts.remove(productId);
                                    }
                                    purchasePlanApproved = false;
                                  });
                                },
                        ),
                      ],
                    ),
                    const Divider(),
                    _purchasingDetail(
                      'Current stock',
                      '${_formatRecommendationQuantity(currentStock)} $unit',
                    ),
                    _purchasingDetail(
                      'Minimum stock',
                      '${_formatRecommendationQuantity(minimumStock)} $unit',
                    ),
                    _purchasingDetail(
                      'Average daily sales',
                      '${_formatRecommendationQuantity(averageDailySales)} $unit',
                    ),
                    _purchasingDetail(
                      'Estimated days remaining',
                      remainingDays == null
                          ? 'Not available (no recorded sales)'
                          : '${_formatRecommendationQuantity(_recommendationNumber(remainingDays))} days',
                    ),
                    _purchasingDetail(
                      'Suggested reorder',
                      '${_formatRecommendationQuantity(suggestedQuantity)} $unit',
                      emphasize: true,
                    ),
                    _purchasingDetail(
                      'Purchase price',
                      product == null
                          ? 'Unavailable'
                          : '₹${product.purchasePrice.toStringAsFixed(2)} / $unit',
                    ),
                    _purchasingDetail(
                      'Estimated purchase cost',
                      product == null
                          ? 'Unavailable'
                          : '₹${cost.toStringAsFixed(2)}',
                      emphasize: true,
                    ),
                    if (product == null)
                      const Padding(
                        padding: EdgeInsets.only(top: 8),
                        child: Text(
                          'Purchase price could not be matched to this product.',
                          style: TextStyle(color: Colors.red),
                        ),
                      ),
                  ],
                ),
              ),
            );
          }),
          if (restockRecommendations.isNotEmpty) ...[
            const SizedBox(height: 12),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'Purchase approval',
                      style: TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    const SizedBox(height: 12),
                    _purchasingDetail('Selected products', '$selectedCount'),
                    _purchasingDetail(
                      'Estimated total',
                      '₹${selectedTotal.toStringAsFixed(2)}',
                      emphasize: true,
                    ),
                    const SizedBox(height: 12),
                    SizedBox(
                      width: double.infinity,
                      child: FilledButton.icon(
                        onPressed: widget.userRole != 'owner' || selectedCount == 0
                            ? null : _approvePurchasePlan,
                        icon: const Icon(Icons.verified_outlined),
                        label: const Text('Review and approve plan'),
                      ),
                    ),
                    if (widget.userRole == 'owner' && purchasePlanApproved)
                      const Padding(
                        padding: EdgeInsets.only(top: 10),
                        child: Text(
                          'Plan approved for review. No order has been placed.',
                          style: TextStyle(
                            color: Colors.green,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
                    const SizedBox(height: 8),
                    if (widget.userRole == 'owner') const Text(
                      'KiranaAI does not place orders or contact suppliers. '
                      'Owner approval here confirms the plan only.',
                      style: TextStyle(color: Colors.black54),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }

  /// Builds one label and value row in the Purchasing page.
  Widget _purchasingDetail(
    String label,
    String value, {
    bool emphasize = false,
  }) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Text(
              label,
              style: TextStyle(
                color: Colors.black54,
                fontWeight: emphasize ? FontWeight.w600 : FontWeight.normal,
              ),
            ),
          ),
          const SizedBox(width: 12),
          Flexible(
            child: Text(
              value,
              textAlign: TextAlign.end,
              style: TextStyle(
                fontWeight: emphasize ? FontWeight.bold : FontWeight.w500,
                color: emphasize ? const Color(0xFF16845B) : null,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _loadSalesHistory() async {
    setState(() => _salesLoading = true);
    try {
      final rows = await ApiService.getSalesHistory();
      if (mounted) setState(() { _salesHistory = rows; _salesLoading = false; });
    } catch (error) {
      if (mounted) {
        setState(() => _salesLoading = false);
        showSnackBar('Unable to load sales: $error', isError: true);
      }
    }
  }

  Future<void> _addSaleCartItem() async {
    final productId = _saleProductId;
    final quantity = double.tryParse(_saleQuantityController.text.trim());
    if (productId == null || quantity == null || quantity <= 0) {
      showSnackBar('Choose a product and enter a valid quantity.', isError: true);
      return;
    }
    Product? product;
    for (final candidate in products) { if (candidate.id == productId) product = candidate; }
    if (product == null) return;
    final alreadyAdded = _saleCart[productId] ?? 0;
    if (alreadyAdded + quantity > product.quantity) {
      showSnackBar('Quantity exceeds recorded stock for ${product.name}.', isError: true);
      return;
    }
    setState(() {
      _saleCart[productId] = alreadyAdded + quantity;
      _saleQuantityController.text = '1';
    });
  }

  Future<void> _submitSale() async {
    if (_saleCart.isEmpty) return;
    setState(() => _saleSubmitting = true);
    try {
      final items = _saleCart.entries.map((entry) => {
        'product_id': entry.key, 'quantity': entry.value, 'discount_amount': 0,
      }).toList();
      await ApiService.createSale(items: items, paymentMethod: _salePaymentMethod);
      if (!mounted) return;
      setState(() => _saleCart.clear());
      await loadBackendData();
      await _loadSalesHistory();
      if (mounted) showSnackBar('Sale recorded and stock deducted.');
    } catch (error) {
      if (mounted) showSnackBar('Sale could not be recorded: $error', isError: true);
    } finally {
      if (mounted) setState(() => _saleSubmitting = false);
    }
  }

  Future<void> _askInventoryAi() async {
    final question = _aiQuestionController.text.trim();
    if (question.isEmpty || _aiLoading) return;
    setState(() {
      _aiMessages.add({'role': 'user', 'text': question});
      _aiQuestionController.clear();
      _aiLoading = true;
    });
    try {
      final response = await ApiService.getInventoryAgentAnswer(question);
      final resultText = const JsonEncoder.withIndent('  ').convert(response['results'] ?? response);
      if (mounted) setState(() {
        _aiMessages.add({'role': 'assistant', 'text': resultText});
        _aiLoading = false;
      });
    } catch (error) {
      if (mounted) setState(() {
        _aiMessages.add({'role': 'assistant', 'text': 'Analysis failed: $error'});
        _aiLoading = false;
      });
    }
  }

  Widget buildSales() {
    double cartTotal = 0;
    for (final entry in _saleCart.entries) {
      for (final product in products) {
        if (product.id == entry.key) cartTotal += product.sellingPrice * entry.value;
      }
    }
    return RefreshIndicator(
      onRefresh: _loadSalesHistory,
      child: ListView(padding: const EdgeInsets.all(20), children: [
        const Text('Sales', style: TextStyle(fontSize: 28, fontWeight: FontWeight.bold)),
        const SizedBox(height: 8),
        const Text('The backend validates verified, unexpired batch stock and deducts inventory atomically.'),
        const SizedBox(height: 16),
        Card(child: Padding(padding: const EdgeInsets.all(16), child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('New sale', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
            const SizedBox(height: 12),
            DropdownButtonFormField<int>(
              value: _saleProductId,
              decoration: const InputDecoration(labelText: 'Product', border: OutlineInputBorder()),
              items: products.map((p) => DropdownMenuItem(value: p.id,
                child: Text('${p.name} · ${p.quantity} ${p.unit}'))).toList(),
              onChanged: (value) => setState(() => _saleProductId = value),
            ),
            const SizedBox(height: 10),
            Row(children: [
              Expanded(child: TextField(controller: _saleQuantityController,
                keyboardType: const TextInputType.numberWithOptions(decimal: true),
                decoration: const InputDecoration(labelText: 'Quantity', border: OutlineInputBorder()))),
              const SizedBox(width: 10),
              FilledButton(onPressed: _addSaleCartItem, child: const Text('Add')),
            ]),
            if (_saleCart.isNotEmpty) ...[
              const Divider(height: 24),
              ..._saleCart.entries.map((entry) {
                Product? product;
                for (final p in products) { if (p.id == entry.key) product = p; }
                return ListTile(
                  contentPadding: EdgeInsets.zero,
                  title: Text(product?.name ?? 'Product'),
                  subtitle: Text('${entry.value} ${product?.unit ?? ''}'),
                  trailing: IconButton(icon: const Icon(Icons.remove_circle_outline),
                    onPressed: () => setState(() => _saleCart.remove(entry.key))),
                );
              }),
              Text('Estimated bill: ₹${cartTotal.toStringAsFixed(2)}',
                style: const TextStyle(fontWeight: FontWeight.bold)),
              const SizedBox(height: 10),
              DropdownButtonFormField<String>(
                value: _salePaymentMethod,
                decoration: const InputDecoration(labelText: 'Payment method'),
                items: const [
                  DropdownMenuItem(value: 'cash', child: Text('Cash')),
                  DropdownMenuItem(value: 'upi', child: Text('UPI')),
                  DropdownMenuItem(value: 'bank_transfer', child: Text('Bank transfer')),
                ],
                onChanged: (value) => setState(() => _salePaymentMethod = value ?? 'cash'),
              ),
              const SizedBox(height: 12),
              SizedBox(width: double.infinity, child: FilledButton.icon(
                onPressed: _saleSubmitting ? null : _submitSale,
                icon: const Icon(Icons.receipt_long),
                label: Text(_saleSubmitting ? 'Saving sale...' : 'Complete sale'),
              )),
            ],
          ],
        ))),
        const SizedBox(height: 18),
        Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
          const Text('Recent bills', style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
          IconButton(onPressed: _loadSalesHistory, icon: const Icon(Icons.refresh)),
        ]),
        if (_salesLoading) const LinearProgressIndicator(),
        if (!_salesLoading && _salesHistory.isEmpty) const Text('No sales recorded yet.'),
        ..._salesHistory.map((raw) {
          final sale = raw as Map<String, dynamic>;
          final items = sale['items'] as List<dynamic>? ?? [];
          final amount = (sale['total_amount'] as num?)?.toDouble() ?? 0;
          return Card(child: ListTile(
            leading: const Icon(Icons.receipt_long, color: Color(0xFF16845B)),
            title: Text('₹${amount.toStringAsFixed(2)}'),
            subtitle: Text('${items.length} item lines · ${sale['payment_method'] ?? 'payment not recorded'}'),
            trailing: Text('#${sale['sale_id']}'),
          ));
        }),
      ]),
    );
  }

  Widget buildAiAssistant() {
    return Column(children: [
      const Padding(padding: EdgeInsets.fromLTRB(20, 20, 20, 8),
        child: Align(alignment: Alignment.centerLeft, child: Text('KiranaAI Assistant',
          style: TextStyle(fontSize: 26, fontWeight: FontWeight.bold)))),
      const Padding(padding: EdgeInsets.symmetric(horizontal: 20),
        child: Align(alignment: Alignment.centerLeft,
          child: Text('Read-only inventory, sales and purchasing insights.'))),
      Expanded(child: ListView.builder(
        padding: const EdgeInsets.all(16),
        itemCount: _aiMessages.length,
        itemBuilder: (context, index) {
          final message = _aiMessages[index];
          final isUser = message['role'] == 'user';
          return Align(alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
            child: Container(
              constraints: const BoxConstraints(maxWidth: 700),
              margin: const EdgeInsets.only(bottom: 12),
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: isUser ? const Color(0xFFD9EFE5) : Colors.white,
                borderRadius: BorderRadius.circular(14),
              ),
              child: SelectableText(message['text'] ?? ''),
            ));
        },
      )),
      if (_aiLoading) const LinearProgressIndicator(),
      SafeArea(top: false, child: Padding(padding: const EdgeInsets.all(12),
        child: Row(children: [
          Expanded(child: TextField(
            controller: _aiQuestionController, minLines: 1, maxLines: 4,
            decoration: const InputDecoration(
              hintText: 'Ask: Which products are low in stock?',
              border: OutlineInputBorder(),
            ),
            onSubmitted: (_) => _askInventoryAi(),
          )),
          const SizedBox(width: 8),
          IconButton.filled(
            onPressed: _aiLoading ? null : _askInventoryAi,
            icon: const Icon(Icons.send),
          ),
        ]),
      )),
    ]);
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

        Card(
          child: ListTile(
            leading: const Icon(Icons.logout, color: Colors.red),
            title: const Text('Sign out'),
            subtitle: const Text('Securely end this session'),
            onTap: widget.onLogout,
          ),
        ),

        Card(

          child: ListTile(

            leading: const Icon(Icons.store),

            title: Text(widget.shopName),

            subtitle: Text('Signed in as ${widget.userRole}'),

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
      'quantity': 0,
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
                const Padding(
                  padding: EdgeInsets.only(bottom: 12),
                  child: Text(
                    'Products start with zero stock. Add opening stock later with a batch number and expiry date.',
                    style: TextStyle(color: Colors.black54),
                  ),
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

