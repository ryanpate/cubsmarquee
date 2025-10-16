def get_prime_factors(number):
    factors = []
    a = []
    b = []
    divisor = 2
    while divisor <= number:
        if number % divisor == 0:
            factors.append(divisor)
            number = number // divisor
            a.append(number)
        else:
            divisor += 1
            b.append(divisor)
    print(a)
    print(b)
    return factors


# commands used in solution video for reference
if __name__ == '__main__':
    print(get_prime_factors(630))  # [2, 3, 3, 5, 7]
    print(get_prime_factors(13))  # [13]