class UserModel {
  final int id;
  final String email;
  final String username;
  final String role;
  final bool isActive;
  final String? createdAt;

  const UserModel({
    required this.id,
    required this.email,
    required this.username,
    required this.role,
    required this.isActive,
    this.createdAt,
  });

  factory UserModel.fromJson(Map<String, dynamic> json) => UserModel(
    id:        json['id'] as int? ?? 0,
    email:     json['email'] as String? ?? '',
    username:  json['username'] as String? ?? '',
    role:      (json['role'] as String? ?? 'USER').toUpperCase(),
    isActive:  json['is_active'] as bool? ?? true,
    createdAt: json['created_at'] as String?,
  );

  bool get isAdmin => role == 'ADMIN';
}
