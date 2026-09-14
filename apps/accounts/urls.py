from django.urls import path

from apps.accounts import views

app_name = "accounts"

urlpatterns = [
    path("register/", views.RegisterView.as_view(), name="register"),
    path("verify-sent/", views.VerificationSentView.as_view(), name="verification_sent"),
    path("verify/<str:token>/", views.VerifyEmailView.as_view(), name="verify_email"),
    path("verify-resend/", views.ResendVerificationView.as_view(), name="resend_verification"),
    path("login/", views.PhoneLoginView.as_view(), name="login"),
    path("login/verify/", views.PhoneLoginVerifyView.as_view(), name="login_verify"),
    path("login/resend/", views.PhoneLoginResendView.as_view(), name="login_resend"),
    path("login/email/", views.EmailLoginView.as_view(), name="login_email"),
    path("profile/phone/", views.PhoneChangeView.as_view(), name="phone_change"),
    path("profile/phone/verify/", views.PhoneChangeVerifyView.as_view(), name="phone_change_verify"),
    path("profile/phone/resend/", views.PhoneChangeResendView.as_view(), name="phone_change_resend"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    path("profile/", views.ProfileView.as_view(), name="profile"),
    path("profile/password/", views.PasswordChangeView.as_view(), name="password_change"),
    path("password-reset/", views.PasswordResetView.as_view(), name="password_reset"),
    path("password-reset/done/", views.PasswordResetDoneView.as_view(), name="password_reset_done"),
    path("password-reset/<uidb64>/<token>/", views.PasswordResetConfirmView.as_view(), name="password_reset_confirm"),
    path("password-reset/complete/", views.PasswordResetCompleteView.as_view(), name="password_reset_complete"),
    path("addresses/", views.AddressListView.as_view(), name="address_list"),
    path("addresses/new/", views.AddressCreateView.as_view(), name="address_create"),
    path("addresses/<int:pk>/edit/", views.AddressUpdateView.as_view(), name="address_edit"),
    path("addresses/<int:pk>/delete/", views.AddressDeleteView.as_view(), name="address_delete"),
    path("addresses/<int:pk>/default/", views.AddressSetDefaultView.as_view(), name="address_default"),
]
