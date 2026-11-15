import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;

/// ---------------------------------------------------------
/// SERVICE: KiranaAI API Service
/// Purpose:
/// Centralise communication between Flutter and FastAPI.
/// Handle login, secure token storage and authenticated requests.
/// ---------------------------------------------------------

class ApiService {
  // Android emulator: use http://10.0.2.2:8000.
  // Chrome / Windows: use http://127.0.0.1:8000.
  static String get baseUrl {
    if (kIsWeb) {
      return 'http://127.0.0.1:8000';
    }

    switch (defaultTargetPlatform) {
      case TargetPlatform.android:
        return 'http://10.0.2.2:8000';
      default:
        return 'http://127.0.0.1:8000';
    }
  }

  static const Duration timeoutDuration = Duration(seconds: 15);

  // Secure storage keeps the access token outside ordinary application preferences.
  static const FlutterSecureStorage _secureStorage =
      FlutterSecureStorage();

  static const String _tokenKey = 'kiranaai_access_token';
  static const String _activeShopKey = 'kiranaai_active_shop_id';

  /// FUNCTION: Build headers for authenticated API requests.
  /// Purpose: Add the saved bearer token when the user is logged in.
  static Future<Map<String, String>> _authorizedHeaders({
    bool jsonContent = false,
  }) async {
    final headers = <String, String>{};

    if (jsonContent) {
      headers['Content-Type'] = 'application/json';
    }

    final token = await _secureStorage.read(key: _tokenKey);

    if (token != null && token.isNotEmpty) {
      headers['Authorization'] = 'Bearer $token';
    }

    return headers;
  }

  /// FUNCTION: Log in a user.
  /// Method: POST
  /// Endpoint: /auth/login
  /// Purpose: Verify email and password, then securely save the access token.
  /// Note: The FastAPI endpoint expects form fields named username and password.
  static Future<Map<String, dynamic>> login({
    required String email,
    required String password,
  }) async {
    final response = await http
        .post(
          Uri.parse('$baseUrl/auth/login'),
          headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json',
          },
          body: {
            'username': email.trim().toLowerCase(),
            'password': password,
          },
        )
        .timeout(timeoutDuration);

    if (response.statusCode == 200) {
      final responseData =
          jsonDecode(response.body) as Map<String, dynamic>;
      final token = responseData['access_token'] as String?;

      if (token == null || token.isEmpty) {
        throw Exception('The server did not return an access token.');
      }

      await _secureStorage.write(key: _tokenKey, value: token);
      try {
        final shops = await refreshMyShops();
        if (shops.isEmpty) {
          await logout();
          throw Exception('This account is not linked to an active shop.');
        }
      } catch (_) {
        await logout();
        rethrow;
      }

      return responseData;
    }

    if (response.statusCode == 401) {
      throw Exception('Incorrect email or password.');
    }

    if (response.statusCode == 403) {
      throw Exception('This account is inactive.');
    }

    throw Exception('Login failed: ${response.body}');
  }

  /// FUNCTION: Get the current saved access token.
  /// Purpose: Read the login token from secure storage.
  static Future<String?> getAccessToken() async {
    return _secureStorage.read(key: _tokenKey);
  }

  /// FUNCTION: Check whether a login token is stored.
  /// Purpose: Help the app decide whether a login screen is needed.
  static Future<bool> hasAccessToken() async {
    final token = await getAccessToken();
    return token != null && token.isNotEmpty;
  }

  /// FUNCTION: Log out the current user.
  /// Purpose: Remove the saved access token from secure storage.
  static Future<void> logout() async {
    await _secureStorage.delete(key: _tokenKey);
    await _secureStorage.delete(key: _activeShopKey);
  }

  /// Returns the authenticated user's active shop memberships.
  static Future<List<Map<String, dynamic>>> getMyShops() async {
    final response = await http
        .get(
          Uri.parse('$baseUrl/auth/shops'),
          headers: await _authorizedHeaders(),
        )
        .timeout(timeoutDuration);

    if (response.statusCode == 200) {
      return (jsonDecode(response.body) as List<dynamic>)
          .map((item) => item as Map<String, dynamic>)
          .toList();
    }
    if (response.statusCode == 401) {
      await logout();
      throw Exception('Your session has expired. Please log in again.');
    }
    throw Exception('Unable to load your shops: ${response.body}');
  }

  /// Loads memberships and selects the saved shop, or the first active shop.
  static Future<List<Map<String, dynamic>>> refreshMyShops() async {
    final shops = await getMyShops();
    final savedId = await _secureStorage.read(key: _activeShopKey);
    final savedIsValid = savedId != null && shops.any(
      (shop) => shop['shop_id'].toString() == savedId,
    );
    if (!savedIsValid) {
      if (shops.isEmpty) {
        await _secureStorage.delete(key: _activeShopKey);
      } else {
        await setActiveShop((shops.first['shop_id'] as num).toInt());
      }
    }
    return shops;
  }

  /// Stores a shop only if the authenticated user has an active membership.
  static Future<void> setActiveShop(int shopId) async {
    final shops = await getMyShops();
    final allowed = shops.any(
      (shop) => (shop['shop_id'] as num).toInt() == shopId,
    );
    if (!allowed) {
      throw Exception('You do not have access to the selected shop.');
    }
    await _secureStorage.write(key: _activeShopKey, value: shopId.toString());
  }

  /// Returns the active shop membership stored for this session.
  static Future<Map<String, dynamic>?> getActiveShop() async {
    final shopId = await _secureStorage.read(key: _activeShopKey);
    if (shopId == null) return null;
    final shops = await getMyShops();
    for (final shop in shops) {
      if (shop['shop_id'].toString() == shopId) return shop;
    }
    await _secureStorage.delete(key: _activeShopKey);
    return null;
  }

  static Future<int> _requireActiveShopId() async {
    final value = await _secureStorage.read(key: _activeShopKey);
    final shopId = int.tryParse(value ?? '');
    if (shopId == null || shopId <= 0) {
      throw Exception('No active shop selected. Please sign in again.');
    }
    return shopId;
  }

  /// FUNCTION: Get the currently authenticated user.
  /// Method: GET
  /// Endpoint: /auth/me
  /// Purpose: Validate the saved token and retrieve the user's latest details.
  static Future<Map<String, dynamic>> getCurrentUser() async {
    final response = await http
        .get(
          Uri.parse('$baseUrl/auth/me'),
          headers: await _authorizedHeaders(),
        )
        .timeout(timeoutDuration);

    if (response.statusCode == 200) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    }

    if (response.statusCode == 401) {
      await logout();
      throw Exception('Your session has expired. Please log in again.');
    }

    throw Exception('Unable to load user details: ${response.body}');
  }

  /// FUNCTION: Check Backend Connection.
  /// Method: GET
  /// Endpoint: /health
  /// Purpose: Verify that the FastAPI backend is running.
  static Future<bool> checkConnection() async {
    try {
      final response = await http
          .get(Uri.parse('$baseUrl/health'))
          .timeout(timeoutDuration);

      return response.statusCode == 200;
    } catch (error) {
      debugPrint('Backend connection error: $error');
      return false;
    }
  }

  /// FUNCTION: Get All Products.
  /// Method: GET
  /// Endpoint: /products
  /// Purpose: Retrieve products from the backend database.
  static Future<List<dynamic>> getProducts() async {
    final shopId = await _requireActiveShopId();
    final uri = Uri.parse('$baseUrl/products').replace(
      queryParameters: {'shop_id': shopId.toString()},
    );
    final response = await http
        .get(
          uri,
          headers: await _authorizedHeaders(),
        )
        .timeout(timeoutDuration);

    if (response.statusCode == 200) {
      return jsonDecode(response.body) as List<dynamic>;
    }

    throw Exception(
      'Unable to load products. Status: ${response.statusCode}',
    );
  }

  /// FUNCTION: Get Inventory Summary.
  /// Method: GET
  /// Endpoint: /inventory/summary
  /// Purpose: Retrieve inventory dashboard statistics.
  static Future<Map<String, dynamic>> getInventorySummary() async {
    final shopId = await _requireActiveShopId();
    final uri = Uri.parse('$baseUrl/inventory/summary').replace(
      queryParameters: {'shop_id': shopId.toString()},
    );
    final response = await http
        .get(
          uri,
          headers: await _authorizedHeaders(),
        )
        .timeout(timeoutDuration);

    if (response.statusCode == 200) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    }

    throw Exception(
      'Unable to load inventory summary. Status: ${response.statusCode}',
    );
  }

  /// FUNCTION: Get Smart Restock Recommendations.
  /// Method: GET
  /// Endpoint: /inventory/restock-recommendations
  /// Purpose: Retrieve stock coverage and suggested reorder quantities.
  static Future<Map<String, dynamic>> getRestockRecommendations({
    int days = 30,
    int warningDays = 7,
  }) async {
    final shopId = await _requireActiveShopId();
    final uri = Uri.parse(
      '$baseUrl/inventory/restock-recommendations',
    ).replace(
      queryParameters: {
        'shop_id': shopId.toString(),
        'days': days.toString(),
        'warning_days': warningDays.toString(),
      },
    );

    final response = await http
        .get(
          uri,
          headers: await _authorizedHeaders(),
        )
        .timeout(timeoutDuration);

    if (response.statusCode == 200) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    }

    throw Exception(
      'Unable to load restock recommendations: ${response.body}',
    );
  }

  /// FUNCTION: Add New Product.
  /// Method: POST
  /// Endpoint: /products
  /// Purpose: Create a product in the backend database.
  static Future<Map<String, dynamic>> addProduct(
    Map<String, dynamic> productData,
  ) async {
    final shopId = await _requireActiveShopId();
    final uri = Uri.parse('$baseUrl/products').replace(
      queryParameters: {'shop_id': shopId.toString()},
    );
    final response = await http
        .post(
          uri,
          headers: await _authorizedHeaders(jsonContent: true),
          body: jsonEncode(productData),
        )
        .timeout(timeoutDuration);

    if (response.statusCode == 201) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    }

    throw Exception('Unable to add product: ${response.body}');
  }

  /// FUNCTION: Update Existing Product.
  /// Method: PUT
  /// Endpoint: /products/{productId}
  /// Purpose: Update product details in the backend database.
  static Future<Map<String, dynamic>> updateProduct(
    int productId,
    Map<String, dynamic> productData,
  ) async {
    final shopId = await _requireActiveShopId();
    final uri = Uri.parse('$baseUrl/products/$productId').replace(
      queryParameters: {'shop_id': shopId.toString()},
    );
    final response = await http
        .put(
          uri,
          headers: await _authorizedHeaders(jsonContent: true),
          body: jsonEncode(productData),
        )
        .timeout(timeoutDuration);

    if (response.statusCode == 200) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    }

    throw Exception('Unable to update product: ${response.body}');
  }

  /// FUNCTION: Delete Product.
  /// Method: DELETE
  /// Endpoint: /products/{productId}
  /// Purpose: Delete a product from the backend database.
  static Future<void> deleteProduct(int productId) async {
    final shopId = await _requireActiveShopId();
    final uri = Uri.parse('$baseUrl/products/$productId').replace(
      queryParameters: {'shop_id': shopId.toString()},
    );
    final response = await http
        .delete(
          uri,
          headers: await _authorizedHeaders(),
        )
        .timeout(timeoutDuration);

    if (response.statusCode != 200) {
      throw Exception('Unable to delete product: ${response.body}');
    }
  }
}
