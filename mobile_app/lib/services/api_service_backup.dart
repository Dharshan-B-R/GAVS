import 'package:flutter/foundation.dart';
import 'dart:convert';
import 'package:http/http.dart' as http;

/// ---------------------------------------------------------
/// SERVICE: KiranaAI API Service
/// Purpose:
/// Centralise communication between Flutter and FastAPI.
/// ---------------------------------------------------------

class ApiService {
  // Android emulator: use http://10.0.2.2:8000
  // Chrome / Windows: use http://127.0.0.1:8000
  static const String baseUrl = 'http://127.0.0.1:8000';

  static const Duration timeoutDuration = Duration(seconds: 15);

  /// FUNCTION: Check Backend Connection
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

  /// FUNCTION: Get All Products
  /// Method: GET
  /// Endpoint: /products
  /// Purpose: Retrieve all active products from PostgreSQL.
  static Future<List<dynamic>> getProducts() async {
    final response = await http
        .get(Uri.parse('$baseUrl/products'))
        .timeout(timeoutDuration);

    if (response.statusCode == 200) {
      return jsonDecode(response.body) as List<dynamic>;
    }

    throw Exception(
      'Unable to load products. Status: ${response.statusCode}',
    );
  }

  /// FUNCTION: Get Inventory Summary
  /// Method: GET
  /// Endpoint: /inventory/summary
  /// Purpose: Retrieve inventory dashboard statistics.
  static Future<Map<String, dynamic>> getInventorySummary() async {
    final response = await http
        .get(Uri.parse('$baseUrl/inventory/summary'))
        .timeout(timeoutDuration);

    if (response.statusCode == 200) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    }

    throw Exception(
      'Unable to load inventory summary. Status: ${response.statusCode}',
    );
  }

  /// FUNCTION: Add New Product
  /// Method: POST
  /// Endpoint: /products
  /// Purpose: Create a product in the backend database.
  static Future<Map<String, dynamic>> addProduct(
    Map<String, dynamic> productData,
  ) async {
    final response = await http
        .post(
          Uri.parse('$baseUrl/products'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode(productData),
        )
        .timeout(timeoutDuration);

    if (response.statusCode == 201) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    }

    throw Exception(
      'Unable to add product: ${response.body}',
    );
  }

  /// FUNCTION: Update Existing Product
  /// Method: PUT
  /// Endpoint: /products/{productId}
  /// Purpose: Update product details in the backend database.
  static Future<Map<String, dynamic>> updateProduct(
    int productId,
    Map<String, dynamic> productData,
  ) async {
    final response = await http
        .put(
          Uri.parse('$baseUrl/products/$productId'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode(productData),
        )
        .timeout(timeoutDuration);

    if (response.statusCode == 200) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    }

    throw Exception(
      'Unable to update product: ${response.body}',
    );
  }

  /// FUNCTION: Delete Product
  /// Method: DELETE
  /// Endpoint: /products/{productId}
  /// Purpose: Delete a product from the backend database.
  static Future<void> deleteProduct(int productId) async {
    final response = await http
        .delete(Uri.parse('$baseUrl/products/$productId'))
        .timeout(timeoutDuration);

    if (response.statusCode != 200) {
      throw Exception(
        'Unable to delete product: ${response.body}',
      );
    }
  }
}
