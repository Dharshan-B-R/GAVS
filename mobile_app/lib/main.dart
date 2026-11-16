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
      return SupplierHomePage(onLogout: _onLogout, identity: identity);
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
                      const SizedBox(height: 8),
                      TextButton(
                        onPressed: _busy ? null : () async {
                          final registered = await Navigator.of(context).push<bool>(
                            MaterialPageRoute(builder: (_) => const RegistrationScreen()),
                          );
                          if (registered == true && mounted) widget.onLogin();
                        },
                        child: const Text('Create an Owner or Supplier account'),
                      ),
                      TextButton(
                        onPressed: _busy ? null : () async {
                          final accepted = await Navigator.of(context).push<bool>(
                            MaterialPageRoute(builder: (_) => const EmployeeInvitationScreen()),
                          );
                          if (accepted == true && mounted) widget.onLogin();
                        },
                        child: const Text('Join a shop with an employee invitation'),
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
  List<Map<String, dynamic>> _myShops = [];
  int? _activeShopId;
  String? _activeShopName;



  
  // Backend-generated restock recommendation state.
  List<Map<String, dynamic>> restockRecommendations = [];
  final Set<int> selectedRestockProducts = <int>{};
  bool isRestockLoading = false;
  String? restockError;
  List<dynamic> _shopSuppliers = [];
  List<dynamic> _supplierDirectory = [];
  int? _supplierDirectorySelection;
  List<dynamic> _purchaseProposals = [];
  List<dynamic> _purchaseOrders = [];
  int? _selectedSupplierId;
  final TextEditingController _budgetController = TextEditingController();
  final TextEditingController _supplierIdController = TextEditingController();
  bool _purchasePlanningLoading = false;
  bool _budgetSaving = false;
  double _committedBudget = 0;
  double _remainingBudget = 0;
  final TextEditingController _employeeEmailController = TextEditingController();
  final TextEditingController _legacyCustomerIdController = TextEditingController();
  List<dynamic> _employees = [];
  bool _employeesLoading = false;
  final TextEditingController _saleQuantityController = TextEditingController(text: '1');
  final TextEditingController _aiQuestionController = TextEditingController();
  int? _saleProductId;
  String _salePaymentMethod = 'cash';
  final Map<int, double> _saleCart = {};
  List<dynamic> _salesHistory = [];
  bool _salesLoading = false;
  bool _saleSubmitting = false;
  bool _aiLoading = false;
  bool _intelligenceLoading = false;
  String? _intelligenceError;
  Map<String, dynamic> _intelligenceSnapshot = {};
  List<dynamic> _festivalEvents = [];
  Map<String, dynamic> _availabilityCoverage = {};
  bool _availabilityCapturing = false;
  List<dynamic> _shopCustomers = [];
  List<dynamic> _supplierIssues = [];
  List<dynamic> _intelligenceAlerts = [];
  List<dynamic> _dailySummaries = [];
  List<dynamic> _feedbackHistory = [];
  final List<Map<String, String>> _aiMessages = [
    {'role': 'assistant', 'text': 'Ask about low stock, expiry, dead stock, sales trends, forecasts or reorder recommendations.'},
  ];
/// Loads initial backend data when the application starts.

  @override

  void initState() {
    super.initState();
    loadBackendData();
    _loadMyShops();
  }

  Future<void> _loadMyShops() async {
    try {
      final shops = await ApiService.refreshMyShops();
      final active = await ApiService.getActiveShop();
      if (mounted) setState(() {
        _myShops = shops;
        _activeShopId = (active?['shop_id'] as num?)?.toInt();
        _activeShopName = active?['name']?.toString();
      });
    } catch (error) {
      if (mounted) showSnackBar('Could not load shop memberships: $error', isError: true);
    }
  }

  Future<void> _switchShop(int shopId) async {
    try {
      await ApiService.setActiveShop(shopId);
      final active = await ApiService.getActiveShop();
      if (mounted) setState(() {
        _activeShopId = shopId;
        _activeShopName = active?['name']?.toString();
        products.clear();
        inventorySummary = {};
        restockRecommendations.clear();
        selectedRestockProducts.clear();
        _salesHistory.clear();
        _purchaseProposals.clear();
        _purchaseOrders.clear();
      });
      await loadBackendData();
      await loadRestockRecommendations();
      await _loadSalesHistory();
      if (mounted) showSnackBar('Switched to ${active?['name'] ?? 'selected shop'}.');
    } catch (error) {
      if (mounted) showSnackBar('Could not switch shop: $error', isError: true);
    }
  }



  /// Releases the search controller when this screen is removed.

  @override

  void dispose() {
    searchController.dispose();
    _saleQuantityController.dispose();
    _aiQuestionController.dispose();
    _budgetController.dispose();
    _supplierIdController.dispose();
    _employeeEmailController.dispose();
    _legacyCustomerIdController.dispose();
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

          title: const Text('Archive product?'),

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

              child: const Text('Archive'),

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

        showSnackBar('Product archived. Historical records were preserved.');

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
      buildIntelligence(),
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
          } else if (index == 5) {
            _loadPhase2Intelligence();
          } else if (index == 6 && widget.userRole == 'owner') {
            _loadEmployees();
          }

        },

        destinations: const [
          NavigationDestination(icon: Icon(Icons.home_outlined), selectedIcon: Icon(Icons.home), label: 'Home'),
          NavigationDestination(icon: Icon(Icons.inventory_2_outlined), selectedIcon: Icon(Icons.inventory_2), label: 'Inventory'),
          NavigationDestination(icon: Icon(Icons.point_of_sale_outlined), selectedIcon: Icon(Icons.point_of_sale), label: 'Sales'),
          NavigationDestination(icon: Icon(Icons.shopping_cart_outlined), selectedIcon: Icon(Icons.shopping_cart), label: 'Purchasing'),
          NavigationDestination(icon: Icon(Icons.auto_awesome_outlined), selectedIcon: Icon(Icons.auto_awesome), label: 'AI Assistant'),
          NavigationDestination(icon: Icon(Icons.insights_outlined), selectedIcon: Icon(Icons.insights), label: 'Intelligence'),
          NavigationDestination(icon: Icon(Icons.settings_outlined), selectedIcon: Icon(Icons.settings), label: 'Settings'),
        ],
      ),

      floatingActionButton: FloatingActionButton.extended(

        onPressed: () => setState(() => selectedIndex = 4),

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

            child: Column(

              crossAxisAlignment: CrossAxisAlignment.start,

              children: [

                const Icon(

                  Icons.storefront,

                  color: Colors.white,

                  size: 35,

                ),

                SizedBox(height: 12),

                Text(

                  'Welcome, ${widget.userRole == 'owner' ? 'Shop Owner' : 'Employee'}!',

                  style: TextStyle(

                    color: Colors.white,

                    fontSize: 22,

                    fontWeight: FontWeight.bold,

                  ),

                ),

                SizedBox(height: 6),

                Text(

                  '${_activeShopName ?? widget.shopName} · Manage your shop smarter with KiranaAI.',

                  style: const TextStyle(color: Colors.white),

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

              IconButton(
                tooltip: 'Set up opening batch for legacy stock',
                onPressed: showOpeningBatchDialog,
                icon: const Icon(Icons.playlist_add_outlined),
              ),
              IconButton(
                tooltip: 'Verify received batches',
                onPressed: showBatchVerificationDialog,
                icon: const Icon(Icons.fact_check_outlined),
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
                if (value == 'edit') {
                  showEditProductDialog(product);
                } else if (value == 'delete') {
                  deleteProduct(product);
                }
              },
              itemBuilder: (context) => [
                const PopupMenuItem(value: 'edit', child: Text('Edit product details')),
                if (widget.userRole == 'owner')
                  const PopupMenuItem(value: 'delete', child: Text('Archive product')),
              ],

            ),

          ],

        ),

      ),

    );

  }



  Future<void> showOpeningBatchDialog() async {
    final stocked = products.where((product) => product.quantity > 0).toList();
    if (stocked.isEmpty) {
      showSnackBar('No positive legacy stock needs an opening batch.');
      return;
    }
    final details = await showDialog<Map<String, dynamic>>(
      context: context,
      builder: (dialogContext) => OpeningBatchDialog(products: stocked),
    );
    if (details == null) return;
    try {
      await ApiService.createOpeningBatch(
        productId: details['product_id'] as int,
        batchNumber: details['batch_number'] as String,
        expiryDate: details['expiry_date'] as String,
      );
      await loadBackendData();
      await showBatchVerificationDialog();
    } catch (error) {
      if (mounted) showSnackBar('Opening batch setup failed: $error', isError: true);
    }
  }

  Future<void> showBatchVerificationDialog() async {
    try {
      final batches = await ApiService.getInventoryBatches();
      if (!mounted) return;
      if (batches.isEmpty) {
        showSnackBar('There are no remaining batches to verify.');
        return;
      }
      final changed = await showDialog<bool>(
        context: context,
        builder: (dialogContext) => BatchVerificationDialog(
          batches: batches.cast<Map<String, dynamic>>(),
        ),
      );
      if (changed == true) await loadBackendData();
    } catch (error) {
      if (mounted) showSnackBar('Could not load inventory batches: $error', isError: true);
    }
  }

  Future<void> showEditProductDialog(Product product) async {
    final result = await showDialog<Map<String, dynamic>>(
      context: context,
      builder: (dialogContext) => EditProductDialog(product: product),
    );
    if (result == null) return;
    try {
      await ApiService.updateProduct(product.id, result);
      await loadBackendData();
      if (mounted) showSnackBar('Product details updated.');
    } catch (error) {
      if (mounted) showSnackBar('Product update failed: $error', isError: true);
    }
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


  Future<void> _loadEmployees() async {
    if (widget.userRole != 'owner') return;
    setState(() => _employeesLoading = true);
    try {
      final rows = await ApiService.getEmployees();
      if (mounted) setState(() { _employees = rows; _employeesLoading = false; });
    } catch (error) {
      if (mounted) {
        setState(() => _employeesLoading = false);
        showSnackBar('Could not load employees: $error', isError: true);
      }
    }
  }

  Future<void> _inviteEmployee() async {
    final email = _employeeEmailController.text.trim();
    if (!email.contains('@')) {
      showSnackBar('Enter a valid employee email.', isError: true);
      return;
    }
    try {
      final result = await ApiService.inviteEmployee(email);
      _employeeEmailController.clear();
      if (!mounted) return;
      await showDialog<void>(
        context: context,
        builder: (dialogContext) => AlertDialog(
          title: const Text('Employee invitation created'),
          content: SelectableText(
            'Share this one-time invitation token securely with $email:\n\n${result['invitation_token']}\n\nIt expires in 7 days.',
          ),
          actions: [TextButton(onPressed: () => Navigator.pop(dialogContext), child: const Text('Close'))],
        ),
      );
      await _loadEmployees();
    } catch (error) {
      if (mounted) showSnackBar('Invitation failed: $error', isError: true);
    }
  }

  Future<void> _toggleEmployee(int userId, bool active) async {
    try {
      await ApiService.setEmployeeStatus(userId, active);
      await _loadEmployees();
    } catch (error) {
      if (mounted) showSnackBar('Could not update employee: $error', isError: true);
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
        ApiService.getDistributorDirectory(),
      ]);
      if (!mounted) return;
      final suppliers = (results[0] as List<dynamic>)
          .where((raw) => raw['is_active'] == true).toList();
      final budget = results[3] as Map<String, dynamic>;
      setState(() {
        _shopSuppliers = suppliers;
        _purchaseProposals = results[1] as List<dynamic>;
        _purchaseOrders = results[2] as List<dynamic>;
        _supplierDirectory = results[4] as List<dynamic>;
        _supplierDirectorySelection ??= _supplierDirectory.isNotEmpty
            ? (_supplierDirectory.first['supplier_id'] as num).toInt() : null;
        if (_selectedSupplierId == null ||
            !suppliers.any((raw) => (raw['supplier_id'] as num).toInt() == _selectedSupplierId)) {
          _selectedSupplierId = suppliers.isNotEmpty
              ? (suppliers.first['supplier_id'] as num).toInt() : null;
        }
        if (_supplierDirectorySelection == null ||
            !_supplierDirectory.any((raw) => (raw['supplier_id'] as num).toInt() == _supplierDirectorySelection)) {
          _supplierDirectorySelection = _supplierDirectory.isNotEmpty
              ? (_supplierDirectory.first['supplier_id'] as num).toInt() : null;
        }
        _budgetController.text = budget['available_amount']?.toString() ?? '0.00';
        _committedBudget = (double.tryParse(budget['committed_amount']?.toString() ?? '') ?? 0);
        _remainingBudget = (double.tryParse(budget['remaining_amount']?.toString() ?? '') ?? 0);
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

  Future<void> _connectSelectedSupplier() async {
    final id = _supplierDirectorySelection;
    if (id == null) return;
    try {
      await ApiService.connectSupplier(id);
      await _loadPurchasePlanningData();
      if (mounted) showSnackBar('Supplier connected to this shop.');
    } catch (error) {
      if (mounted) showSnackBar('Could not connect supplier: $error', isError: true);
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
    final receipt = await showDialog<Map<String, dynamic>>(
      context: context,
      builder: (dialogContext) => ReceivePurchaseDialog(items: items, products: products),
    );
    if (receipt == null) return;
    try {
      await ApiService.receivePurchaseOrder(
        (order['purchase_id'] as num).toInt(),
        (receipt['items'] as List<dynamic>).cast<Map<String, dynamic>>(),
        invoiceNumber: receipt['invoice_number']?.toString(),
        invoiceAmount: (receipt['invoice_amount'] as num?)?.toDouble(),
      );
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
        leadTimeDays: 7,
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
    await _createPurchaseProposal();
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
          if (widget.userRole == 'owner') ...[
            const SizedBox(height: 16),
            Card(child: Padding(padding: const EdgeInsets.all(16), child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('Cash budget', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
                const SizedBox(height: 8),
                TextField(controller: _budgetController,
                  keyboardType: const TextInputType.numberWithOptions(decimal: true),
                  decoration: const InputDecoration(labelText: 'Available purchase budget (INR)', prefixText: '₹', border: OutlineInputBorder())),
                const SizedBox(height: 8),
                Text('Committed: ₹${_committedBudget.toStringAsFixed(2)} · Remaining: ₹${_remainingBudget.toStringAsFixed(2)}',
                  style: const TextStyle(color: Colors.black54)),
                const SizedBox(height: 8),
                Align(alignment: Alignment.centerRight, child: FilledButton(
                  onPressed: _budgetSaving ? null : _savePurchaseBudget,
                  child: Text(_budgetSaving ? 'Saving...' : 'Save budget'))),
                const Divider(),
                const Text('Connected suppliers', style: TextStyle(fontWeight: FontWeight.bold)),
                if (_shopSuppliers.isEmpty)
                  const Padding(padding: EdgeInsets.symmetric(vertical: 8),
                    child: Text('No suppliers connected yet. Enter an active supplier ID to connect one.')),
                if (_shopSuppliers.isNotEmpty)
                  DropdownButtonFormField<int>(
                    initialValue: _selectedSupplierId,
                    decoration: const InputDecoration(labelText: 'Select supplier'),
                    items: _shopSuppliers.map((raw) {
                      final supplier = raw as Map<String, dynamic>;
                      return DropdownMenuItem<int>(
                        value: (supplier['supplier_id'] as num).toInt(),
                        child: Text(supplier['name'].toString()),
                      );
                    }).toList(),
                    onChanged: (value) => setState(() => _selectedSupplierId = value),
                  ),
                const SizedBox(height: 8),
                if (_supplierDirectory.isNotEmpty)
                  Row(children: [
                    Expanded(child: DropdownButtonFormField<int>(
                      initialValue: _supplierDirectorySelection,
                      decoration: const InputDecoration(labelText: 'Find a supplier'),
                      items: _supplierDirectory.map((raw) {
                        final supplier = raw as Map<String, dynamic>;
                        return DropdownMenuItem<int>(
                          value: (supplier['supplier_id'] as num).toInt(),
                          child: Text(supplier['name'].toString()),
                        );
                      }).toList(),
                      onChanged: (value) => setState(() => _supplierDirectorySelection = value),
                    )),
                    const SizedBox(width: 8),
                    FilledButton.tonal(onPressed: _connectSelectedSupplier, child: const Text('Connect')),
                  ])
                else
                  const Text('No other active suppliers are registered yet. A supplier can create an account from the login screen.'),
                const SizedBox(height: 8),
                ExpansionTile(
                  tilePadding: EdgeInsets.zero,
                  title: const Text('Connect by supplier ID'),
                  children: [
                    Row(children: [
                      Expanded(child: TextField(controller: _supplierIdController,
                        keyboardType: TextInputType.number,
                        decoration: const InputDecoration(labelText: 'Supplier ID', border: OutlineInputBorder()))),
                      const SizedBox(width: 8),
                      FilledButton.tonal(onPressed: _connectSupplierById, child: const Text('Connect')),
                    ]),
                  ],
                ),
              ],
            ))),
            const SizedBox(height: 12),
          ],
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
          if (widget.userRole == 'owner' && _purchasePlanningLoading)
            const LinearProgressIndicator(),
          if (widget.userRole == 'owner' && _purchaseProposals.isNotEmpty) ...[
            const SizedBox(height: 20),
            const Text('Purchase proposals', style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
            ..._purchaseProposals.map((raw) {
              final proposal = raw as Map<String, dynamic>;
              final id = (proposal['proposal_id'] as num).toInt();
              final status = proposal['status'].toString();
              final total = proposal['total_amount']?.toString() ?? '0.00';
              return Card(child: Padding(padding: const EdgeInsets.all(14), child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Proposal #$id · $status', style: const TextStyle(fontWeight: FontWeight.bold)),
                  Text('Total: ₹$total'),
                  if (status == 'pending') Row(children: [
                    TextButton(onPressed: () => _decideProposal(id, false), child: const Text('Reject')),
                    const Spacer(),
                    FilledButton(onPressed: () => _decideProposal(id, true), child: const Text('Approve')),
                  ]),
                  if (status == 'approved')
                    SizedBox(width: double.infinity, child: FilledButton(
                      onPressed: () => _executeProposal(id),
                      child: const Text('Create internal purchase order'))),
                ],
              )));
            }),
          ],
          if (widget.userRole == 'owner' && _purchaseOrders.isNotEmpty) ...[
            const SizedBox(height: 20),
            const Text('Internal purchase orders', style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
            ..._purchaseOrders.map((raw) {
              final order = raw as Map<String, dynamic>;
              final status = order['status'].toString();
              return Card(child: ListTile(
                leading: const Icon(Icons.local_shipping_outlined),
                title: Text(order['purchase_order_number']?.toString() ?? 'Purchase order'),
                subtitle: Text('Status: $status · ₹${order['total_amount']} · Promised: ${order['expected_delivery_date'] ?? 'not set'}'),
                trailing: (status == 'ordered' || status == 'confirmed')
                    ? Wrap(mainAxisSize: MainAxisSize.min, spacing: 4, children: [
                        IconButton(
                          tooltip: 'Set supplier-promised delivery date',
                          icon: const Icon(Icons.event_available_outlined),
                          onPressed: () => _setExpectedDeliveryDate(order),
                        ),
                        IconButton(
                          tooltip: 'Receive goods',
                          icon: const Icon(Icons.inventory),
                          onPressed: () => _receivePurchaseOrder(order),
                        ),
                      ])
                    : const Icon(Icons.check_circle, color: Colors.green),
              ));
            }),
          ],
          if (widget.userRole == 'owner' && restockRecommendations.isNotEmpty) ...[
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
                        label: const Text('Create proposal for owner approval'),
                      ),
                    ),
                    const SizedBox(height: 8),
                    if (widget.userRole == 'owner') const Text(
                      'Creating a proposal does not place an order. Approve it first, then create an internal purchase order.',
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



  Future<void> _loadIntelligenceContext() async {
    try {
      final values = await Future.wait([
        ApiService.getFestivalCalendar(),
        ApiService.getAvailabilitySnapshotCoverage(),
        ApiService.getShopCustomers(),
        ApiService.getSupplierIssues(status: 'open'),
        ApiService.getShopSuppliers(),
        ApiService.getIntelligenceAlerts(),
        ApiService.getIntelligenceDailySummaries(limit: 7),
        ApiService.getRecommendationFeedback(limit: 10),
      ]);
      if (!mounted) return;
      setState(() {
        _festivalEvents = values[0] as List<dynamic>;
        _availabilityCoverage = values[1] as Map<String, dynamic>;
        _shopCustomers = values[2] as List<dynamic>;
        _supplierIssues = values[3] as List<dynamic>;
        _shopSuppliers = values[4] as List<dynamic>;
        _intelligenceAlerts = values[5] as List<dynamic>;
        _dailySummaries = values[6] as List<dynamic>;
        _feedbackHistory = values[7] as List<dynamic>;
      });
    } catch (_) {
      // The primary intelligence response remains usable if optional context
      // endpoints are temporarily unavailable.
    }
  }

  Future<void> _captureAvailabilitySnapshot() async {
    if (_availabilityCapturing) return;
    setState(() => _availabilityCapturing = true);
    try {
      final result = await ApiService.captureDailyAvailability();
      await _loadIntelligenceContext();
      if (mounted) showSnackBar(result['message']?.toString() ?? 'Availability snapshot saved.');
    } catch (error) {
      if (mounted) showSnackBar('Could not capture availability: $error', isError: true);
    } finally {
      if (mounted) setState(() => _availabilityCapturing = false);
    }
  }





  Future<void> _acknowledgeAlert(int alertId) async {
    try {
      await ApiService.acknowledgeIntelligenceAlert(alertId);
      await _loadIntelligenceContext();
      if (mounted) showSnackBar('Alert acknowledged.');
    } catch (error) {
      if (mounted) showSnackBar('Could not acknowledge alert: $error', isError: true);
    }
  }

  Future<void> _generateDailySummary() async {
    try {
      await ApiService.generateIntelligenceDailySummary();
      await _loadIntelligenceContext();
      if (mounted) showSnackBar('Daily intelligence summary generated.');
    } catch (error) {
      if (mounted) showSnackBar('Could not generate summary: $error', isError: true);
    }
  }

  Future<void> _recordRecommendationFeedback() async {
    if (products.isEmpty) {
      showSnackBar('Add products before recording recommendation feedback.', isError: true);
      return;
    }
    int selectedProductId = products.first.id;
    String decision = 'accepted';
    final actualQty = TextEditingController();
    final notes = TextEditingController();
    final accepted = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(builder: (context, updateDialog) =>
        AlertDialog(
          title: const Text('Recommendation feedback'),
          content: Column(mainAxisSize: MainAxisSize.min, children: [
            DropdownButtonFormField<int>(
              value: selectedProductId,
              decoration: const InputDecoration(labelText: 'Product'),
              items: products.map((product) => DropdownMenuItem<int>(
                value: product.id, child: Text(product.name),
              )).toList(),
              onChanged: (value) { if (value != null) updateDialog(() => selectedProductId = value); },
            ),
            DropdownButtonFormField<String>(
              value: decision,
              decoration: const InputDecoration(labelText: 'Decision'),
              items: const [
                DropdownMenuItem(value: 'accepted', child: Text('Accepted')),
                DropdownMenuItem(value: 'dismissed', child: Text('Dismissed')),
                DropdownMenuItem(value: 'adjusted', child: Text('Adjusted quantity')),
              ],
              onChanged: (value) { if (value != null) updateDialog(() => decision = value); },
            ),
            if (decision == 'adjusted')
              TextField(controller: actualQty,
                keyboardType: const TextInputType.numberWithOptions(decimal: true),
                decoration: const InputDecoration(labelText: 'Actual planned quantity')),
            TextField(controller: notes, maxLines: 2,
              decoration: const InputDecoration(labelText: 'Reason / notes (optional)')),
          ]),
          actions: [
            TextButton(onPressed: () => Navigator.pop(dialogContext, false), child: const Text('Cancel')),
            FilledButton(onPressed: () => Navigator.pop(dialogContext, true), child: const Text('Save feedback')),
          ],
        ),
      ),
    );
    if (accepted == true) {
      final product = products.firstWhere((item) => item.id == selectedProductId);
      Map<String, dynamic>? recommendation;
      for (final item in restockRecommendations) {
        if ((item['product_id'] as num?)?.toInt() == selectedProductId) {
          recommendation = item;
          break;
        }
      }
      final recommendedQty = recommendation == null
          ? null
          : _recommendationNumber(recommendation['suggested_quantity']);
      final actual = double.tryParse(actualQty.text.trim());
      if (decision == 'adjusted' && (actual == null || actual < 0)) {
        if (mounted) showSnackBar('Enter a valid actual quantity.', isError: true);
      } else {
        try {
          await ApiService.submitRecommendationFeedback(
            recommendationKey: 'reorder:$selectedProductId:${DateTime.now().toIso8601String().substring(0, 10)}',
            decision: decision,
            productId: product.id,
            recommendedQuantity: recommendedQty,
            actualQuantity: decision == 'adjusted' ? actual : null,
            notes: notes.text.trim().isEmpty ? null : notes.text.trim(),
          );
          await _loadIntelligenceContext();
          if (mounted) showSnackBar('Recommendation feedback saved.');
        } catch (error) {
          if (mounted) showSnackBar('Could not save feedback: $error', isError: true);
        }
      }
    }
    actualQty.dispose();
    notes.dispose();
  }

  Future<void> _reportSupplierIssue() async {
    if (_shopSuppliers.isEmpty) {
      try {
        _shopSuppliers = await ApiService.getShopSuppliers();
      } catch (_) {}
    }
    if (_shopSuppliers.isEmpty) {
      if (mounted) showSnackBar('Connect a supplier before recording an issue.', isError: true);
      return;
    }
    int selectedSupplier = (_shopSuppliers.first['supplier_id'] as num).toInt();
    String severity = 'medium';
    final type = TextEditingController();
    final description = TextEditingController();
    final purchaseIdText = TextEditingController();
    final accepted = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(builder: (context, updateDialog) =>
        AlertDialog(
          title: const Text('Report supplier issue'),
          content: SingleChildScrollView(child: Column(mainAxisSize: MainAxisSize.min, children: [
            DropdownButtonFormField<int>(
              value: selectedSupplier,
              decoration: const InputDecoration(labelText: 'Supplier'),
              items: _shopSuppliers.map((raw) {
                final supplier = raw as Map<String, dynamic>;
                return DropdownMenuItem<int>(
                  value: (supplier['supplier_id'] as num).toInt(),
                  child: Text(supplier['name'].toString()),
                );
              }).toList(),
              onChanged: (value) { if (value != null) updateDialog(() => selectedSupplier = value); },
            ),
            TextField(controller: type, decoration: const InputDecoration(labelText: 'Issue type (short label)')),
            TextField(controller: description, maxLines: 3,
              decoration: const InputDecoration(labelText: 'Describe the issue')),
            TextField(controller: purchaseIdText, keyboardType: TextInputType.number,
              decoration: const InputDecoration(labelText: 'Related purchase ID (optional)')),
            DropdownButtonFormField<String>(
              value: severity,
              decoration: const InputDecoration(labelText: 'Severity'),
              items: const [
                DropdownMenuItem(value: 'low', child: Text('Low')),
                DropdownMenuItem(value: 'medium', child: Text('Medium')),
                DropdownMenuItem(value: 'high', child: Text('High')),
                DropdownMenuItem(value: 'critical', child: Text('Critical')),
              ],
              onChanged: (value) { if (value != null) updateDialog(() => severity = value); },
            ),
          ])),
          actions: [
            TextButton(onPressed: () => Navigator.pop(dialogContext, false), child: const Text('Cancel')),
            FilledButton(onPressed: () => Navigator.pop(dialogContext, true), child: const Text('Save issue')),
          ],
        ),
      ),
    );
    if (accepted == true && type.text.trim().isNotEmpty && description.text.trim().isNotEmpty) {
      try {
        await ApiService.createSupplierIssue(
          supplierId: selectedSupplier,
          purchaseId: int.tryParse(purchaseIdText.text.trim()),
          issueType: type.text.trim(),
          description: description.text.trim(), severity: severity);
        await _loadIntelligenceContext();
        if (mounted) showSnackBar('Supplier issue recorded.');
      } catch (error) {
        if (mounted) showSnackBar('Could not record supplier issue: $error', isError: true);
      }
    }
    type.dispose();
    description.dispose();
    purchaseIdText.dispose();
  }

  Future<void> _resolveSupplierIssue(int issueId) async {
    try {
      await ApiService.resolveSupplierIssue(issueId);
      await _loadIntelligenceContext();
      if (mounted) showSnackBar('Supplier issue marked resolved.');
    } catch (error) {
      if (mounted) showSnackBar('Could not resolve supplier issue: $error', isError: true);
    }
  }


  Future<void> _assignLegacyCustomer() async {
    final customerId = int.tryParse(_legacyCustomerIdController.text.trim());
    if (customerId == null || customerId <= 0) {
      showSnackBar('Enter a valid legacy customer ID.', isError: true);
      return;
    }
    try {
      await ApiService.assignLegacyCustomerToShop(customerId);
      _legacyCustomerIdController.clear();
      await _loadIntelligenceContext();
      await _loadPhase2Intelligence();
      if (mounted) showSnackBar('Legacy customer assigned to this shop.');
    } catch (error) {
      if (mounted) showSnackBar('Could not assign customer: $error', isError: true);
    }
  }

  Future<void> _createKhataCustomer() async {
    final name = TextEditingController();
    final phone = TextEditingController();
    final accepted = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Add shop customer'),
        content: Column(mainAxisSize: MainAxisSize.min, children: [
          TextField(controller: name, decoration: const InputDecoration(labelText: 'Customer name')),
          TextField(controller: phone, keyboardType: TextInputType.phone,
            decoration: const InputDecoration(labelText: 'Phone (optional)')),
        ]),
        actions: [
          TextButton(onPressed: () => Navigator.pop(dialogContext, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(dialogContext, true), child: const Text('Save customer')),
        ],
      ),
    );
    if (accepted == true && name.text.trim().isNotEmpty) {
      try {
        await ApiService.createShopCustomer({'name': name.text.trim(), 'phone': phone.text.trim()});
        await _loadIntelligenceContext();
        if (mounted) showSnackBar('Customer added to this shop.');
      } catch (error) {
        if (mounted) showSnackBar('Could not add customer: $error', isError: true);
      }
    }
    name.dispose();
    phone.dispose();
  }

  Future<void> _addKhataEntry(int customerId) async {
    final amount = TextEditingController();
    String kind = 'credit';
    final accepted = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(builder: (context, updateDialog) =>
        AlertDialog(
          title: const Text('Record khata transaction'),
          content: Column(mainAxisSize: MainAxisSize.min, children: [
            DropdownButtonFormField<String>(
              value: kind,
              decoration: const InputDecoration(labelText: 'Transaction'),
              items: const [
                DropdownMenuItem(value: 'credit', child: Text('New credit / udhar')),
                DropdownMenuItem(value: 'repayment', child: Text('Customer repayment')),
              ],
              onChanged: (value) { if (value != null) updateDialog(() => kind = value); },
            ),
            TextField(controller: amount, keyboardType: const TextInputType.numberWithOptions(decimal: true),
              decoration: const InputDecoration(labelText: 'Amount (INR)')),
          ]),
          actions: [
            TextButton(onPressed: () => Navigator.pop(dialogContext, false), child: const Text('Cancel')),
            FilledButton(onPressed: () => Navigator.pop(dialogContext, true), child: const Text('Save')),
          ],
        ),
      ),
    );
    if (accepted == true) {
      final value = double.tryParse(amount.text.trim());
      if (value == null || value <= 0) {
        if (mounted) showSnackBar('Enter a valid positive amount.', isError: true);
      } else {
        try {
          await ApiService.addShopKhataTransaction(customerId, {
            'transaction_type': kind, 'amount': value,
          });
          if (mounted) showSnackBar('Khata transaction recorded.');
          await _openKhataLedger(customerId);
        } catch (error) {
          if (mounted) showSnackBar('Could not record khata transaction: $error', isError: true);
        }
      }
    }
    amount.dispose();
  }

  Future<void> _openKhataLedger(int customerId) async {
    try {
      final ledger = await ApiService.getShopKhataLedger(customerId);
      if (!mounted) return;
      await showDialog<void>(
        context: context,
        builder: (dialogContext) => AlertDialog(
          title: Text(ledger['customer_name']?.toString() ?? 'Customer khata'),
          content: SizedBox(width: 520, child: SingleChildScrollView(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text('Outstanding: ₹${ledger['outstanding_amount'] ?? 0}',
                style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
              const SizedBox(height: 10),
              ...(ledger['transactions'] as List? ?? []).map((raw) {
                final tx = raw as Map<String, dynamic>;
                return ListTile(
                  contentPadding: EdgeInsets.zero,
                  title: Text('${tx['transaction_type']} · ₹${tx['amount']}'),
                  subtitle: Text(tx['created_at']?.toString() ?? ''),
                  trailing: Text('₹${tx['running_balance']}'),
                );
              }),
            ]),
          )),
          actions: [
            TextButton(onPressed: () => Navigator.pop(dialogContext), child: const Text('Close')),
            FilledButton(onPressed: () {
              Navigator.pop(dialogContext);
              _addKhataEntry(customerId);
            }, child: const Text('Add transaction')),
          ],
        ),
      );
    } catch (error) {
      if (mounted) showSnackBar('Could not load customer ledger: $error', isError: true);
    }
  }

  Future<void> _setExpectedDeliveryDate(Map<String, dynamic> order) async {
    final purchaseId = (order['purchase_id'] as num?)?.toInt();
    if (purchaseId == null) return;
    final picked = await showDatePicker(
      context: context,
      initialDate: DateTime.now().add(const Duration(days: 3)),
      firstDate: DateTime.now(),
      lastDate: DateTime.now().add(const Duration(days: 365)),
    );
    if (picked == null) return;
    try {
      await ApiService.setExpectedSupplierDeliveryDate(
        purchaseId, picked.toIso8601String().split('T').first);
      await _loadPurchasePlanning();
      if (mounted) showSnackBar('Supplier-promised delivery date saved.');
    } catch (error) {
      if (mounted) showSnackBar('Could not save delivery date: $error', isError: true);
    }
  }

  Future<void> _configureShopLocation() async {
    final city = TextEditingController();
    final state = TextEditingController();
    final accepted = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Shop location'),
        content: Column(mainAxisSize: MainAxisSize.min, children: [
          TextField(controller: city, decoration: const InputDecoration(labelText: 'City')),
          TextField(controller: state, decoration: const InputDecoration(labelText: 'State')),
        ]),
        actions: [
          TextButton(onPressed: () => Navigator.pop(dialogContext, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(dialogContext, true), child: const Text('Save location')),
        ],
      ),
    );
    if (accepted == true && city.text.trim().isNotEmpty && state.text.trim().isNotEmpty) {
      try {
        await ApiService.updateShopIntelligenceSettings(
          city: city.text.trim(), state: state.text.trim());
        if (mounted) showSnackBar('Shop location saved for local intelligence.');
      } catch (error) {
        if (mounted) showSnackBar('Could not save shop location: $error', isError: true);
      }
    }
    city.dispose();
    state.dispose();
  }

  Future<void> _addFestivalEvent() async {
    final nameController = TextEditingController();
    DateTime selectedDate = DateTime.now();
    String eventType = 'festival';
    final accepted = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(builder: (context, updateDialog) =>
        AlertDialog(
          title: const Text('Add local festival or event'),
          content: Column(mainAxisSize: MainAxisSize.min, children: [
            TextField(controller: nameController,
              decoration: const InputDecoration(labelText: 'Event name')),
            const SizedBox(height: 12),
            DropdownButtonFormField<String>(
              value: eventType,
              decoration: const InputDecoration(labelText: 'Event type'),
              items: const [
                DropdownMenuItem(value: 'festival', child: Text('Festival')),
                DropdownMenuItem(value: 'local_event', child: Text('Local event')),
                DropdownMenuItem(value: 'promotion', child: Text('Promotion')),
                DropdownMenuItem(value: 'market_day', child: Text('Market day')),
              ],
              onChanged: (value) { if (value != null) updateDialog(() => eventType = value); },
            ),
            const SizedBox(height: 8),
            OutlinedButton.icon(
              icon: const Icon(Icons.calendar_month),
              label: Text('Date: ${selectedDate.toIso8601String().split('T').first}'),
              onPressed: () async {
                final picked = await showDatePicker(
                  context: dialogContext,
                  initialDate: selectedDate,
                  firstDate: DateTime(2020),
                  lastDate: DateTime(2040),
                );
                if (picked != null) updateDialog(() => selectedDate = picked);
              },
            ),
          ]),
          actions: [
            TextButton(onPressed: () => Navigator.pop(dialogContext, false), child: const Text('Cancel')),
            FilledButton(onPressed: () => Navigator.pop(dialogContext, true), child: const Text('Save event')),
          ],
        ),
      ),
    );
    if (accepted == true && nameController.text.trim().isNotEmpty) {
      try {
        await ApiService.addFestivalEvent(
          name: nameController.text.trim(),
          eventDate: selectedDate.toIso8601String().split('T').first,
          eventType: eventType,
        );
        await _loadIntelligenceContext();
        if (mounted) showSnackBar('Local event saved to the shop calendar.');
      } catch (error) {
        if (mounted) showSnackBar('Could not save event: $error', isError: true);
      }
    }
    nameController.dispose();
  }

  Future<void> _compareFestivalEvent(Map<String, dynamic> event) async {
    final eventId = (event['event_id'] as num?)?.toInt();
    if (eventId == null) return;
    try {
      final result = await ApiService.compareSavedFestivalEvent(eventId);
      if (!mounted) return;
      await showDialog<void>(
        context: context,
        builder: (dialogContext) => AlertDialog(
          title: Text('${event['name']} demand comparison'),
          content: SizedBox(width: 520, child: SingleChildScrollView(
            child: SelectableText(const JsonEncoder.withIndent('  ').convert(result)),
          )),
          actions: [TextButton(onPressed: () => Navigator.pop(dialogContext), child: const Text('Close'))],
        ),
      );
    } catch (error) {
      if (mounted) showSnackBar('Event comparison unavailable: $error', isError: true);
    }
  }

  Future<void> _loadPhase2Intelligence({bool showMessage = false}) async {
    if (_intelligenceLoading) return;
    setState(() {
      _intelligenceLoading = true;
      _intelligenceError = null;
    });
    try {
      final result = await ApiService.getPhase2IntelligenceSnapshot();
      if (!mounted) return;
      setState(() {
        _intelligenceSnapshot = result;
        _intelligenceLoading = false;
      });
      await _loadIntelligenceContext();
      if (showMessage) showSnackBar('Intelligence refreshed.');
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _intelligenceError = error.toString();
        _intelligenceLoading = false;
      });
      if (showMessage) showSnackBar('Intelligence refresh failed: $error', isError: true);
    }
  }

  Widget _intelligenceMetric(String title, String value, IconData icon) {
    return Card(child: ListTile(
      leading: Icon(icon, color: const Color(0xFF16845B)),
      title: Text(value, style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
      subtitle: Text(title),
    ));
  }

  Widget _intelligenceResultCard(String key, dynamic value) {
    final body = const JsonEncoder.withIndent('  ').convert(value);
    return Card(child: ExpansionTile(
      title: Text(key.replaceAll('_', ' ').toUpperCase(),
        style: const TextStyle(fontWeight: FontWeight.w600)),
      subtitle: Text(value is Map && value['status'] != null
          ? value['status'].toString()
          : 'Evidence and limitations'),
      children: [
        Padding(
          padding: const EdgeInsets.all(14),
          child: Align(alignment: Alignment.centerLeft, child: SelectableText(body)),
        ),
      ],
    ));
  }

  Widget buildIntelligence() {
    final results = _intelligenceSnapshot['results'];
    final specialistResults = results is Map<String, dynamic>
        ? results
        : <String, dynamic>{};
    final evidence = _intelligenceSnapshot['evidence_summary'];
    final safety = _intelligenceSnapshot['safety'];

    return RefreshIndicator(
      onRefresh: () => _loadPhase2Intelligence(),
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          const Text('Shop Intelligence',
            style: TextStyle(fontSize: 28, fontWeight: FontWeight.bold)),
          const SizedBox(height: 6),
          const Text('Read-only insights from recorded shop data. Recommendations never place orders.'),
          const SizedBox(height: 14),
          FilledButton.icon(
            onPressed: _intelligenceLoading ? null : () => _loadPhase2Intelligence(showMessage: true),
            icon: const Icon(Icons.insights),
            label: Text(_intelligenceLoading ? 'Refreshing intelligence…' : 'Refresh intelligence'),
          ),
          if (_intelligenceLoading) const LinearProgressIndicator(),
          if (_intelligenceError != null)
            Card(color: Theme.of(context).colorScheme.errorContainer,
              child: Padding(padding: const EdgeInsets.all(14),
                child: Text('Could not load intelligence: $_intelligenceError'))),
          if (evidence is Map) ...[
            const SizedBox(height: 12),
            _intelligenceMetric('Specialist results', '${evidence['specialist_result_count'] ?? 0}', Icons.hub_outlined),
            if (evidence['partial'] == true)
              const Text('Some specialists need more event parameters or recorded evidence.',
                style: TextStyle(color: Colors.orange)),
          ],



          const SizedBox(height: 16),
          Card(child: Padding(padding: const EdgeInsets.all(14), child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('Supplier issues',
                style: TextStyle(fontSize: 17, fontWeight: FontWeight.bold)),
              const SizedBox(height: 6),
              const Text('Record delivery, quality, short-supply or invoice issues. Linked purchase issues contribute to supplier issue-rate evidence.'),
              Align(alignment: Alignment.centerRight,
                child: TextButton.icon(
                  onPressed: _reportSupplierIssue,
                  icon: const Icon(Icons.report_problem_outlined),
                  label: const Text('Report issue'),
                )),
              if (_supplierIssues.isEmpty)
                const Text('No open supplier issues.'),
              ..._supplierIssues.take(6).map((raw) {
                final issue = raw as Map<String, dynamic>;
                final id = (issue['issue_id'] as num).toInt();
                return ListTile(
                  contentPadding: EdgeInsets.zero,
                  title: Text(issue['issue_type']?.toString() ?? 'Supplier issue'),
                  subtitle: Text('${issue['severity']} · ${issue['description']}'),
                  trailing: IconButton(
                    tooltip: 'Resolve issue',
                    icon: const Icon(Icons.check_circle_outline),
                    onPressed: () => _resolveSupplierIssue(id),
                  ),
                );
              }),
            ],
          ))),
          const SizedBox(height: 16),
          Card(child: Padding(padding: const EdgeInsets.all(14), child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('Customer khata',
                style: TextStyle(fontSize: 17, fontWeight: FontWeight.bold)),
              const SizedBox(height: 6),
              const Text('Shop-scoped customer credit and repayment ledger. Historical unassigned customers are excluded until an owner assigns them.'),
              Align(alignment: Alignment.centerRight,
                child: TextButton.icon(
                  onPressed: _createKhataCustomer,
                  icon: const Icon(Icons.person_add_alt_1),
                  label: const Text('Add customer'),
                )),
              if (_shopCustomers.isEmpty)
                const Text('No shop customers yet.'),
              ..._shopCustomers.take(8).map((raw) {
                final customer = raw as Map<String, dynamic>;
                final id = (customer['customer_id'] as num).toInt();
                return ListTile(
                  contentPadding: EdgeInsets.zero,
                  leading: const Icon(Icons.person_outline),
                  title: Text(customer['name']?.toString() ?? 'Customer'),
                  subtitle: Text(customer['phone']?.toString() ?? 'No phone recorded'),
                  trailing: IconButton(
                    tooltip: 'View khata ledger',
                    icon: const Icon(Icons.receipt_long_outlined),
                    onPressed: () => _openKhataLedger(id),
                  ),
                );
              }),
              if (widget.userRole == 'owner') ...[
                const Divider(),
                const Text('Assign an existing legacy customer'),
                const SizedBox(height: 6),
                Row(children: [
                  Expanded(child: TextField(
                    controller: _legacyCustomerIdController,
                    keyboardType: TextInputType.number,
                    decoration: const InputDecoration(
                      labelText: 'Legacy customer ID',
                      border: OutlineInputBorder(),
                    ),
                  )),
                  const SizedBox(width: 8),
                  FilledButton.tonal(
                    onPressed: _assignLegacyCustomer,
                    child: const Text('Assign'),
                  ),
                ]),
              ],
            ],
          ))),
          const SizedBox(height: 16),
          Card(child: Padding(padding: const EdgeInsets.all(14), child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('Availability evidence',
                style: TextStyle(fontSize: 17, fontWeight: FontWeight.bold)),
              const SizedBox(height: 6),
              const Text('Capture today’s saleable batch stock. Repeated daily snapshots help the forecast distinguish low sales from stockout days.'),
              const SizedBox(height: 10),
              FilledButton.tonalIcon(
                onPressed: _availabilityCapturing ? null : _captureDailyAvailability,
                icon: const Icon(Icons.camera_alt_outlined),
                label: Text(_availabilityCapturing ? 'Capturing…' : 'Capture today’s availability'),
              ),
              if ((_availabilityCoverage['days'] as List?)?.isNotEmpty == true)
                Text('${(_availabilityCoverage['days'] as List).length} recorded snapshot dates'),
            ],
          ))),
          Card(child: Padding(padding: const EdgeInsets.all(14), child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('Local festival calendar',
                style: TextStyle(fontSize: 17, fontWeight: FontWeight.bold)),
              const SizedBox(height: 6),
              const Text('Add local events for later comparison with your shop’s recorded sales.'),
              if (widget.userRole == 'owner')
                Align(alignment: Alignment.centerRight,
                  child: TextButton.icon(
                    onPressed: _addFestivalEvent,
                    icon: const Icon(Icons.add),
                    label: const Text('Add event'),
                  )),
              if (widget.userRole == 'owner')
                Align(alignment: Alignment.centerRight,
                  child: TextButton.icon(
                    onPressed: _configureShopLocation,
                    icon: const Icon(Icons.location_on_outlined),
                    label: const Text('Set shop location'),
                  )),
              if (_festivalEvents.isEmpty)
                const Text('No local events saved yet.'),
              ..._festivalEvents.take(8).map((raw) {
                final event = raw as Map<String, dynamic>;
                return ListTile(
                  contentPadding: EdgeInsets.zero,
                  title: Text(event['name']?.toString() ?? 'Event'),
                  subtitle: Text('${event['event_date'] ?? ''} · ${event['event_type'] ?? 'festival'}'),
                  trailing: IconButton(
                    tooltip: 'Compare recorded demand',
                    icon: const Icon(Icons.query_stats),
                    onPressed: () => _compareFestivalEvent(event),
                  ),
                );
              }),
            ],
          ))),

          const SizedBox(height: 16),
          Card(child: Padding(padding: const EdgeInsets.all(14), child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(children: [
                const Expanded(child: Text('Daily intelligence summary',
                  style: TextStyle(fontSize: 17, fontWeight: FontWeight.bold))),
                if (widget.userRole == 'owner')
                  IconButton(
                    tooltip: 'Generate summary now',
                    onPressed: _generateDailySummary,
                    icon: const Icon(Icons.summarize_outlined),
                  ),
              ]),
              if (_dailySummaries.isEmpty)
                const Text('No daily summary has been generated yet. Configure the scheduled job or generate one as the shop owner.'),
              ..._dailySummaries.take(3).map((raw) {
                final summary = raw as Map<String, dynamic>;
                final payload = summary['payload'] as Map<String, dynamic>? ?? {};
                final expiry = payload['expiry'] as Map<String, dynamic>? ?? {};
                final stockout = payload['stockout'] as Map<String, dynamic>? ?? {};
                final risks = stockout['summary'] as Map<String, dynamic>? ?? {};
                return ListTile(
                  contentPadding: EdgeInsets.zero,
                  title: Text(summary['summary_date']?.toString() ?? 'Daily summary'),
                  subtitle: Text('Expiry exposure ₹${expiry['estimated_cost_exposure'] ?? 0} · Stockout risks ${risks['stockout'] ?? 0}'),
                  trailing: IconButton(
                    icon: const Icon(Icons.open_in_new),
                    onPressed: () => showDialog<void>(
                      context: context,
                      builder: (dialogContext) => AlertDialog(
                        title: Text('Summary ${summary['summary_date']}'),
                        content: SizedBox(width: 520, child: SingleChildScrollView(
                          child: SelectableText(const JsonEncoder.withIndent('  ').convert(payload)),
                        )),
                        actions: [TextButton(onPressed: () => Navigator.pop(dialogContext), child: const Text('Close'))],
                      ),
                    ),
                  ),
                );
              }),
            ],
          ))),
          Card(child: Padding(padding: const EdgeInsets.all(14), child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Actionable alerts (${_intelligenceAlerts.length})',
                style: const TextStyle(fontSize: 17, fontWeight: FontWeight.bold)),
              if (_intelligenceAlerts.isEmpty)
                const Text('No open intelligence alerts.'),
              ..._intelligenceAlerts.take(8).map((raw) {
                final alert = raw as Map<String, dynamic>;
                final id = (alert['alert_id'] as num).toInt();
                return ListTile(
                  contentPadding: EdgeInsets.zero,
                  title: Text(alert['title']?.toString() ?? 'Alert'),
                  subtitle: Text('${alert['severity']} · ${alert['message']}'),
                  trailing: IconButton(
                    tooltip: 'Acknowledge alert',
                    icon: const Icon(Icons.done),
                    onPressed: () => _acknowledgeAlert(id),
                  ),
                );
              }),
            ],
          ))),
          Card(child: Padding(padding: const EdgeInsets.all(14), child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('Recommendation feedback',
                style: TextStyle(fontSize: 17, fontWeight: FontWeight.bold)),
              const Text('Record whether a reorder suggestion was accepted, dismissed or adjusted.'),
              Align(alignment: Alignment.centerRight,
                child: TextButton.icon(
                  onPressed: _recordRecommendationFeedback,
                  icon: const Icon(Icons.rate_review_outlined),
                  label: const Text('Record feedback'),
                )),
              if (_feedbackHistory.isNotEmpty)
                Text('${_feedbackHistory.length} recent feedback records available'),
            ],
          ))),
          if (specialistResults.isNotEmpty) ...[
            const SizedBox(height: 8),
            ...specialistResults.entries.map((entry) => _intelligenceResultCard(entry.key, entry.value)),
          ] else if (!_intelligenceLoading && _intelligenceError == null)
            const Card(child: Padding(padding: EdgeInsets.all(16),
              child: Text('Tap Refresh intelligence to load expiry, dead stock, stockout, seasonal, supplier and financial insights.'))),
          if (safety is Map) ...[
            const SizedBox(height: 8),
            Card(child: ListTile(
              leading: const Icon(Icons.verified_user_outlined),
              title: const Text('Safety'),
              subtitle: Text('Read-only: ${safety['read_only'] == true ? 'yes' : 'no'} · Purchase orders created: ${safety['purchase_orders_created'] == true ? 'yes' : 'no'}'),
            )),
          ],
          const SizedBox(height: 8),
          const Text('Data gaps are reported explicitly. Festival comparisons need an event date; supplier reliability metrics need promised delivery and receipt quantities.',
            style: TextStyle(fontSize: 12, color: Colors.black54)),
        ],
      ),
    );
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
              initialValue: _saleProductId,
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
                initialValue: _salePaymentMethod,
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

            title: Text(_activeShopName ?? widget.shopName),

            subtitle: Text('Signed in as ${widget.userRole}'),

          ),

        ),



        if (widget.userRole == 'owner') ...[
          const SizedBox(height: 12),
          Card(child: Padding(padding: const EdgeInsets.all(16), child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('Employee access', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
              const SizedBox(height: 8),
              TextField(controller: _employeeEmailController,
                keyboardType: TextInputType.emailAddress,
                decoration: const InputDecoration(labelText: 'Employee email', border: OutlineInputBorder())),
              const SizedBox(height: 8),
              Align(alignment: Alignment.centerRight,
                child: FilledButton.tonal(onPressed: _inviteEmployee, child: const Text('Create invitation'))),
              const Divider(),
              if (_employeesLoading) const LinearProgressIndicator(),
              ..._employees.map((raw) {
                final employee = raw as Map<String, dynamic>;
                final userId = (employee['user_id'] as num).toInt();
                return SwitchListTile(
                  contentPadding: EdgeInsets.zero,
                  title: Text(employee['full_name'].toString()),
                  subtitle: Text(employee['email'].toString()),
                  value: employee['is_active'] == true,
                  onChanged: (active) => _toggleEmployee(userId, active),
                );
              }),
              if (!_employeesLoading && _employees.isEmpty)
                const Text('No employees added yet.'),
            ],
          ))),
        ],

        if (_myShops.length > 1)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 10),
            child: DropdownButtonFormField<int>(
              initialValue: _activeShopId,
              decoration: const InputDecoration(labelText: 'Active shop', border: OutlineInputBorder()),
              items: _myShops.map((shop) => DropdownMenuItem<int>(
                value: (shop['shop_id'] as num).toInt(),
                child: Text(shop['name'].toString()),
              )).toList(),
              onChanged: (value) { if (value != null) _switchShop(value); },
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
  final _minimumController = TextEditingController(text: '0');
  final _purchaseController = TextEditingController(text: '0');
  final _sellingController = TextEditingController(text: '0');
  final _unitController = TextEditingController(text: 'pieces');

  /// Releases all form controllers when the dialog widget is removed.
  @override
  void dispose() {
    _nameController.dispose();
    _categoryController.dispose();
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



class ReceivePurchaseDialog extends StatefulWidget {
  const ReceivePurchaseDialog({super.key, required this.items, required this.products});
  final List<Map<String, dynamic>> items;
  final List<Product> products;

  @override
  State<ReceivePurchaseDialog> createState() => _ReceivePurchaseDialogState();
}

class _ReceivePurchaseDialogState extends State<ReceivePurchaseDialog> {
  final Map<int, TextEditingController> _batchControllers = {};
  final Map<int, TextEditingController> _quantityControllers = {};
  final Map<int, DateTime> _expiryDates = {};
  final TextEditingController _invoiceNumberController = TextEditingController();
  final TextEditingController _invoiceAmountController = TextEditingController();

  @override
  void initState() {
    super.initState();
    for (final item in widget.items) {
      final id = (item['purchase_item_id'] as num).toInt();
      _batchControllers[id] = TextEditingController();
      final ordered = item['ordered_quantity'] ?? item['quantity'] ?? 0;
      _quantityControllers[id] = TextEditingController(text: ordered.toString());
    }
  }

  @override
  void dispose() {
    for (final controller in _batchControllers.values) {
      controller.dispose();
    }
    for (final controller in _quantityControllers.values) {
      controller.dispose();
    }
    _invoiceNumberController.dispose();
    _invoiceAmountController.dispose();
    super.dispose();
  }

  String _productName(int productId) {
    for (final product in widget.products) {
      if (product.id == productId) return product.name;
    }
    return 'Product #$productId';
  }

  void _submit() {
    final result = <Map<String, dynamic>>[];
    for (final item in widget.items) {
      final id = (item['purchase_item_id'] as num).toInt();
      final batch = _batchControllers[id]!.text.trim();
      final expiry = _expiryDates[id];
      final received = double.tryParse(_quantityControllers[id]!.text.trim());
      final ordered = double.tryParse((item['ordered_quantity'] ?? item['quantity'] ?? 0).toString()) ?? 0;
      if (received == null || received < 0 || received > ordered ||
          (received > 0 && (batch.isEmpty || expiry == null))) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Enter a received quantity between zero and ordered quantity. Batch and expiry are required when any quantity is received.')),
        );
        return;
      }
      result.add({
        'purchase_item_id': id,
        'batch_number': received > 0 ? batch : null,
        'expiry_date': received > 0 ? expiry!.toIso8601String().substring(0, 10) : null,
        'received_quantity': received,
      });
    }
    final invoiceNumber = _invoiceNumberController.text.trim();
    final invoiceAmountText = _invoiceAmountController.text.trim();
    final invoiceAmount = double.tryParse(invoiceAmountText);
    if ((invoiceNumber.isEmpty) != invoiceAmountText.isEmpty ||
        (invoiceAmountText.isNotEmpty && (invoiceAmount == null || invoiceAmount <= 0))) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Enter both a valid invoice number and invoice amount, or leave both blank.')),
      );
      return;
    }
    Navigator.of(context).pop({
      'items': result,
      'invoice_number': invoiceNumber.isEmpty ? null : invoiceNumber,
      'invoice_amount': invoiceAmount,
    });
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Receive goods'),
      content: SizedBox(
        width: 520,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: _invoiceNumberController,
                decoration: const InputDecoration(labelText: 'Supplier invoice number (optional)'),
              ),
              TextField(
                controller: _invoiceAmountController,
                keyboardType: const TextInputType.numberWithOptions(decimal: true),
                decoration: const InputDecoration(labelText: 'Actual invoice amount (INR, optional)'),
              ),
              const Divider(height: 24),
              ...widget.items.map((item) {
              final itemId = (item['purchase_item_id'] as num).toInt();
              final productId = (item['product_id'] as num).toInt();
              final expiry = _expiryDates[itemId];
              return Padding(
                padding: const EdgeInsets.only(bottom: 16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(_productName(productId),
                      style: const TextStyle(fontWeight: FontWeight.bold)),
                    Text('Ordered quantity: ${item['ordered_quantity'] ?? item['quantity']}'),
                    TextField(
                      controller: _quantityControllers[itemId],
                      keyboardType: const TextInputType.numberWithOptions(decimal: true),
                      decoration: const InputDecoration(labelText: 'Actually received quantity'),
                    ),
                    TextField(
                      controller: _batchControllers[itemId],
                      decoration: const InputDecoration(labelText: 'Batch number'),
                    ),
                    const SizedBox(height: 8),
                    OutlinedButton.icon(
                      onPressed: () async {
                        final selected = await showDatePicker(
                          context: context,
                          firstDate: DateTime.now(),
                          lastDate: DateTime(2100),
                          initialDate: DateTime.now().add(const Duration(days: 180)),
                        );
                        if (selected != null) setState(() => _expiryDates[itemId] = selected);
                      },
                      icon: const Icon(Icons.calendar_today),
                      label: Text(expiry == null ? 'Select expiry date' :
                        'Expiry: ${expiry.toIso8601String().substring(0, 10)}'),
                    ),
                    const Divider(),
                  ],
                ),
              );
            }),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
        FilledButton(onPressed: _submit, child: const Text('Confirm receipt')),
      ],
    );
  }
}



class SupplierHomePage extends StatefulWidget {
  const SupplierHomePage({super.key, required this.onLogout, required this.identity});
  final Future<void> Function() onLogout;
  final String identity;

  @override
  State<SupplierHomePage> createState() => _SupplierHomePageState();
}

class _SupplierHomePageState extends State<SupplierHomePage> {
  List<dynamic> _orders = [];
  Map<String, dynamic>? _profile;
  bool _loading = true;
  String? _error;
  final Set<int> _confirming = {};

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() { _loading = true; _error = null; });
    try {
      final values = await Future.wait([
        ApiService.getSupplierProfile(),
        ApiService.getSupplierOrders(),
      ]);
      if (mounted) setState(() {
        _profile = values[0] as Map<String, dynamic>;
        _orders = values[1] as List<dynamic>;
        _loading = false;
      });
    } catch (error) {
      if (mounted) setState(() { _loading = false; _error = error.toString(); });
    }
  }

  Future<void> _confirm(int purchaseId) async {
    setState(() => _confirming.add(purchaseId));
    try {
      await ApiService.confirmSupplierOrder(purchaseId);
      await _load();
    } catch (error) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Could not confirm order: $error')));
    } finally {
      if (mounted) setState(() => _confirming.remove(purchaseId));
    }
  }

  @override
  Widget build(BuildContext context) {
    final name = _profile?['name']?.toString() ?? widget.identity;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Distributor workspace'),
        actions: [
          IconButton(onPressed: _load, icon: const Icon(Icons.refresh)),
          IconButton(onPressed: widget.onLogout, icon: const Icon(Icons.logout)),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _load,
        child: ListView(padding: const EdgeInsets.all(20), children: [
          Card(child: Padding(padding: const EdgeInsets.all(18), child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Icon(Icons.local_shipping_outlined, size: 38, color: Color(0xFF16845B)),
              const SizedBox(height: 10),
              Text(name, style: const TextStyle(fontSize: 22, fontWeight: FontWeight.bold)),
              Text(widget.identity),
              if (_profile?['phone'] != null) Text(_profile!['phone'].toString()),
            ],
          ))),
          const SizedBox(height: 20),
          const Text('Purchase orders', style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold)),
          if (_loading) const LinearProgressIndicator(),
          if (_error != null) Text(_error!, style: const TextStyle(color: Colors.red)),
          if (!_loading && _orders.isEmpty) const Padding(
            padding: EdgeInsets.all(18),
            child: Text('No purchase orders have been assigned to this distributor yet.')),
          ..._orders.map((raw) {
            final order = raw as Map<String, dynamic>;
            final id = (order['purchase_id'] as num).toInt();
            final items = order['items'] as List<dynamic>? ?? [];
            return Card(child: Padding(padding: const EdgeInsets.all(14), child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(order['purchase_order_number']?.toString() ?? 'PO #$id',
                  style: const TextStyle(fontWeight: FontWeight.bold)),
                Text('Shop: ${order['shop_name']}'),
                Text('Amount: ₹${order['total_amount']}'),
                Text('Status: ${order['status']}'),
                const Divider(),
                ...items.map((item) => Text('${item['product_name'] ?? 'Product #${item['product_id']}'} · Qty ${item['quantity']} ${item['unit'] ?? ''}')),
                if (order['status'] == 'ordered')
                  Align(alignment: Alignment.centerRight, child: FilledButton(
                    onPressed: _confirming.contains(id) ? null : () => _confirm(id),
                    child: Text(_confirming.contains(id) ? 'Confirming...' : 'Confirm order'),
                  )),
              ],
            )));
          }),
          const Padding(padding: EdgeInsets.only(top: 16),
            child: Text('Order confirmation is recorded in KiranaAI. Actual dispatch and delivery coordination still happen with the supplier.',
              style: TextStyle(color: Colors.black54))),
        ]),
      ),
    );
  }
}


class RegistrationScreen extends StatefulWidget {
  const RegistrationScreen({super.key});

  @override
  State<RegistrationScreen> createState() => _RegistrationScreenState();
}

class _RegistrationScreenState extends State<RegistrationScreen> {
  final _formKey = GlobalKey<FormState>();
  final _name = TextEditingController();
  final _email = TextEditingController();
  final _phone = TextEditingController();
  final _password = TextEditingController();
  final _businessName = TextEditingController();
  final _address = TextEditingController();
  bool _supplier = false;
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _name.dispose(); _email.dispose(); _phone.dispose(); _password.dispose();
    _businessName.dispose(); _address.dispose();
    super.dispose();
  }

  Future<void> _register() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() { _busy = true; _error = null; });
    try {
      if (_supplier) {
        await ApiService.registerSupplier({
          'full_name': _name.text.trim(),
          'email': _email.text.trim(),
          'phone': _phone.text.trim().isEmpty ? null : _phone.text.trim(),
          'password': _password.text,
          'business_name': _businessName.text.trim(),
          'contact_person': _name.text.trim(),
          'address': _address.text.trim().isEmpty ? null : _address.text.trim(),
        });
      } else {
        await ApiService.registerOwner({
          'full_name': _name.text.trim(),
          'email': _email.text.trim(),
          'phone': _phone.text.trim().isEmpty ? null : _phone.text.trim(),
          'password': _password.text,
          'shop_name': _businessName.text.trim(),
          'shop_address': _address.text.trim().isEmpty ? null : _address.text.trim(),
        });
      }
      if (mounted) Navigator.of(context).pop(true);
    } catch (error) {
      if (mounted) setState(() => _error = error.toString().replaceFirst('Exception: ', ''));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Create account')),
      body: Center(child: SingleChildScrollView(
        padding: const EdgeInsets.all(20),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 480),
          child: Card(child: Padding(padding: const EdgeInsets.all(20),
            child: Form(key: _formKey, child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                SegmentedButton<bool>(
                  segments: const [
                    ButtonSegment(value: false, label: Text('Shop Owner'), icon: Icon(Icons.store)),
                    ButtonSegment(value: true, label: Text('Supplier'), icon: Icon(Icons.local_shipping)),
                  ],
                  selected: {_supplier},
                  onSelectionChanged: (value) => setState(() => _supplier = value.first),
                ),
                const SizedBox(height: 16),
                TextFormField(controller: _name,
                  decoration: const InputDecoration(labelText: 'Full name'),
                  validator: (v) => (v == null || v.trim().length < 2) ? 'Enter your name' : null),
                TextFormField(controller: _email,
                  keyboardType: TextInputType.emailAddress,
                  decoration: const InputDecoration(labelText: 'Email'),
                  validator: (v) => (v == null || !v.contains('@')) ? 'Enter a valid email' : null),
                TextFormField(controller: _phone,
                  keyboardType: TextInputType.phone,
                  decoration: const InputDecoration(labelText: 'Phone (optional)')),
                TextFormField(controller: _password, obscureText: true,
                  decoration: const InputDecoration(labelText: 'Password (minimum 8 characters)'),
                  validator: (v) => (v == null || v.length < 8) ? 'Use at least 8 characters' : null),
                TextFormField(controller: _businessName,
                  decoration: InputDecoration(labelText: _supplier ? 'Business name' : 'Shop name'),
                  validator: (v) => (v == null || v.trim().length < 2) ? 'Enter a name' : null),
                TextFormField(controller: _address,
                  decoration: InputDecoration(labelText: _supplier ? 'Business address' : 'Shop address')),
                if (_error != null) Padding(
                  padding: const EdgeInsets.only(top: 12),
                  child: Text(_error!, style: const TextStyle(color: Colors.red))),
                const SizedBox(height: 16),
                FilledButton(
                  onPressed: _busy ? null : _register,
                  child: Text(_busy ? 'Creating account...' : 'Create account'),
                ),
              ],
            )),
          )),
        ),
      )),
    );
  }
}


class EmployeeInvitationScreen extends StatefulWidget {
  const EmployeeInvitationScreen({super.key});

  @override
  State<EmployeeInvitationScreen> createState() => _EmployeeInvitationScreenState();
}

class _EmployeeInvitationScreenState extends State<EmployeeInvitationScreen> {
  final _formKey = GlobalKey<FormState>();
  final _token = TextEditingController();
  final _name = TextEditingController();
  final _password = TextEditingController();
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _token.dispose(); _name.dispose(); _password.dispose();
    super.dispose();
  }

  Future<void> _accept() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() { _busy = true; _error = null; });
    try {
      await ApiService.acceptEmployeeInvitation(
        token: _token.text.trim(),
        fullName: _name.text.trim(),
        password: _password.text,
      );
      if (mounted) Navigator.of(context).pop(true);
    } catch (error) {
      if (mounted) setState(() => _error = error.toString().replaceFirst('Exception: ', ''));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Join a shop')),
    body: Center(child: SingleChildScrollView(
      padding: const EdgeInsets.all(20),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 460),
        child: Card(child: Padding(padding: const EdgeInsets.all(20),
          child: Form(key: _formKey, child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Text('Accept employee invitation',
                style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold)),
              const SizedBox(height: 12),
              TextFormField(controller: _token,
                decoration: const InputDecoration(labelText: 'Invitation token'),
                validator: (v) => (v == null || v.trim().length < 20) ? 'Enter the invitation token' : null),
              TextFormField(controller: _name,
                decoration: const InputDecoration(labelText: 'Full name'),
                validator: (v) => (v == null || v.trim().length < 2) ? 'Enter your name' : null),
              TextFormField(controller: _password, obscureText: true,
                decoration: const InputDecoration(labelText: 'Create password'),
                validator: (v) => (v == null || v.length < 8) ? 'Use at least 8 characters' : null),
              if (_error != null) Padding(
                padding: const EdgeInsets.only(top: 12),
                child: Text(_error!, style: const TextStyle(color: Colors.red))),
              const SizedBox(height: 16),
              FilledButton(onPressed: _busy ? null : _accept,
                child: Text(_busy ? 'Joining...' : 'Accept invitation')),
            ],
          )),
        )),
      ),
    )),
  );
}


class BatchVerificationDialog extends StatefulWidget {
  const BatchVerificationDialog({super.key, required this.batches});
  final List<Map<String, dynamic>> batches;

  @override
  State<BatchVerificationDialog> createState() => _BatchVerificationDialogState();
}

class _BatchVerificationDialogState extends State<BatchVerificationDialog> {
  late final List<Map<String, dynamic>> _batches;
  final Map<int, TextEditingController> _quantities = {};
  final Set<int> _saving = {};
  bool _changed = false;

  @override
  void initState() {
    super.initState();
    _batches = widget.batches.map((item) => Map<String, dynamic>.from(item)).toList();
    for (final batch in _batches) {
      final id = (batch['batch_id'] as num).toInt();
      _quantities[id] = TextEditingController(text: batch['quantity'].toString());
    }
  }

  @override
  void dispose() {
    for (final controller in _quantities.values) {
      controller.dispose();
    }
    super.dispose();
  }

  Future<void> _verify(Map<String, dynamic> batch) async {
    final id = (batch['batch_id'] as num).toInt();
    final quantity = double.tryParse(_quantities[id]!.text.trim());
    if (quantity == null || quantity < 0 || !quantity.isFinite) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Enter a valid physical count.')));
      return;
    }
    setState(() => _saving.add(id));
    try {
      await ApiService.verifyInventoryBatch(id, quantity);
      if (mounted) setState(() {
        batch['is_verified'] = true;
        batch['quantity'] = quantity;
        _changed = true;
        _saving.remove(id);
      });
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Batch ${batch['batch_number']} verified.')));
    } catch (error) {
      if (mounted) {
        setState(() => _saving.remove(id));
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Verification failed: $error')));
      }
    }
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: const Text('Verify inventory batches'),
    content: SizedBox(
      width: 560,
      child: ListView(
        shrinkWrap: true,
        children: _batches.map((batch) {
          final id = (batch['batch_id'] as num).toInt();
          final verified = batch['is_verified'] == true;
          return Card(child: Padding(padding: const EdgeInsets.all(12),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(batch['product_name'].toString(),
                style: const TextStyle(fontWeight: FontWeight.bold)),
              Text('Batch: ${batch['batch_number']} · Expiry: ${batch['expiry_date']}'),
              Text('Recorded quantity: ${batch['quantity']} ${batch['unit']}'),
              if (verified)
                const Text('Verified', style: TextStyle(color: Colors.green, fontWeight: FontWeight.bold))
              else ...[
                TextField(controller: _quantities[id],
                  keyboardType: const TextInputType.numberWithOptions(decimal: true),
                  decoration: const InputDecoration(labelText: 'Physical verified quantity')),
                Align(alignment: Alignment.centerRight, child: FilledButton.tonal(
                  onPressed: _saving.contains(id) ? null : () => _verify(batch),
                  child: Text(_saving.contains(id) ? 'Saving...' : 'Verify batch'))),
              ],
            ]),
          ));
        }).toList(),
      ),
    ),
    actions: [
      TextButton(onPressed: () => Navigator.pop(context, _changed), child: const Text('Done')),
    ],
  );
}


class EditProductDialog extends StatefulWidget {
  const EditProductDialog({super.key, required this.product});
  final Product product;

  @override
  State<EditProductDialog> createState() => _EditProductDialogState();
}

class _EditProductDialogState extends State<EditProductDialog> {
  final _formKey = GlobalKey<FormState>();
  late final TextEditingController _name;
  late final TextEditingController _category;
  late final TextEditingController _minimum;
  late final TextEditingController _purchase;
  late final TextEditingController _selling;
  late final TextEditingController _unit;

  @override
  void initState() {
    super.initState();
    _name = TextEditingController(text: widget.product.name);
    _category = TextEditingController(text: widget.product.category);
    _minimum = TextEditingController(text: widget.product.minimumStock.toString());
    _purchase = TextEditingController(text: widget.product.purchasePrice.toString());
    _selling = TextEditingController(text: widget.product.sellingPrice.toString());
    _unit = TextEditingController(text: widget.product.unit);
  }

  @override
  void dispose() {
    _name.dispose(); _category.dispose(); _minimum.dispose();
    _purchase.dispose(); _selling.dispose(); _unit.dispose();
    super.dispose();
  }

  void _save() {
    if (!_formKey.currentState!.validate()) return;
    Navigator.pop(context, {
      'name': _name.text.trim(),
      'category': _category.text.trim(),
      'minimum_stock': double.parse(_minimum.text.trim()),
      'purchase_price': double.parse(_purchase.text.trim()),
      'selling_price': double.parse(_selling.text.trim()),
      'unit': _unit.text.trim(),
    });
  }

  Widget _field(TextEditingController controller, String label, {bool numeric = false}) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: TextFormField(
        controller: controller,
        keyboardType: numeric ? const TextInputType.numberWithOptions(decimal: true) : TextInputType.text,
        decoration: InputDecoration(labelText: label),
        validator: (value) {
          final text = value?.trim() ?? '';
          if (text.isEmpty) return 'Enter $label';
          if (numeric) {
            final parsed = double.tryParse(text);
            if (parsed == null || !parsed.isFinite || parsed < 0) return 'Enter a valid number';
          }
          return null;
        },
      ),
    );
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: const Text('Edit product'),
    content: SizedBox(width: 420, child: Form(
      key: _formKey,
      child: SingleChildScrollView(child: Column(mainAxisSize: MainAxisSize.min, children: [
        _field(_name, 'Product name'),
        _field(_category, 'Category'),
        _field(_minimum, 'Minimum stock', numeric: true),
        _field(_purchase, 'Purchase price', numeric: true),
        _field(_selling, 'Selling price', numeric: true),
        _field(_unit, 'Unit'),
        const Text('Recorded quantity is changed only through audited batch operations.',
          style: TextStyle(color: Colors.black54)),
      ])),
    )),
    actions: [
      TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
      FilledButton(onPressed: _save, child: const Text('Save changes')),
    ],
  );
}


class OpeningBatchDialog extends StatefulWidget {
  const OpeningBatchDialog({super.key, required this.products});
  final List<Product> products;

  @override
  State<OpeningBatchDialog> createState() => _OpeningBatchDialogState();
}

class _OpeningBatchDialogState extends State<OpeningBatchDialog> {
  final _batch = TextEditingController();
  int? _productId;
  DateTime? _expiry;

  @override
  void initState() {
    super.initState();
    if (widget.products.isNotEmpty) _productId = widget.products.first.id;
  }

  @override
  void dispose() {
    _batch.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: const Text('Set up opening stock batch'),
    content: SizedBox(width: 420, child: Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        const Text('For stock recorded before batch tracking. The existing product quantity will not be increased.'),
        const SizedBox(height: 12),
        DropdownButtonFormField<int>(
          initialValue: _productId,
          decoration: const InputDecoration(labelText: 'Product'),
          items: widget.products.map((product) => DropdownMenuItem(
            value: product.id,
            child: Text('${product.name} · ${product.quantity} ${product.unit}'),
          )).toList(),
          onChanged: (value) => setState(() => _productId = value),
        ),
        TextField(controller: _batch, onChanged: (_) => setState(() {}), decoration: const InputDecoration(labelText: 'Batch number')),
        const SizedBox(height: 8),
        OutlinedButton.icon(
          onPressed: () async {
            final selected = await showDatePicker(
              context: context,
              firstDate: DateTime.now(),
              lastDate: DateTime(2100),
              initialDate: DateTime.now().add(const Duration(days: 180)),
            );
            if (selected != null) setState(() => _expiry = selected);
          },
          icon: const Icon(Icons.calendar_today),
          label: Text(_expiry == null ? 'Select expiry date' :
            'Expiry: ${_expiry!.toIso8601String().substring(0, 10)}'),
        ),
      ],
    )),
    actions: [
      TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
      FilledButton(
        onPressed: _productId == null || _batch.text.trim().isEmpty || _expiry == null
            ? null
            : () => Navigator.pop(context, {
                'product_id': _productId,
                'batch_number': _batch.text.trim(),
                'expiry_date': _expiry!.toIso8601String().substring(0, 10),
              }),
        child: const Text('Create batch'),
      ),
    ],
  );
}
